"""Validate Microsoft PE CodeView / MSF 7 PDB identities without toolchain dependencies."""
from __future__ import annotations

import struct
from pathlib import PurePosixPath


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def pe_identity(data: bytes):
    """Return (PDB GUID bytes, Age) for an RSDS debug entry, or None."""
    try:
        if data[:2] != b"MZ":
            raise ValueError("Invalid PE signature")
        pe = _u32(data, 0x3c)
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("Invalid PE signature")
        count = struct.unpack_from("<H", data, pe + 6)[0]
        size = struct.unpack_from("<H", data, pe + 20)[0]
        opt = pe + 24
        magic = struct.unpack_from("<H", data, opt)[0]
        if magic not in (0x10b, 0x20b):
            raise ValueError("Invalid PE optional header")
        directories = opt + (96 if magic == 0x10b else 112)
        if directories + 56 > opt + size or _u32(data, directories - 4) <= 6:
            return None
        rva, length = struct.unpack_from("<II", data, directories + 48)
        if not rva or not length:
            return None
        offset = None
        for n in range(count):
            section = opt + size + n * 40
            virtual_size, address, raw_size, raw = struct.unpack_from("<IIII", data, section + 8)
            if address <= rva and rva - address + length <= raw_size:
                offset = raw + rva - address
                break
        if offset is None or length % 28 or offset + length > len(data):
            raise ValueError("Invalid PE debug directory")
        identities = set()
        for pos in range(offset, offset + length, 28):
            kind, amount, _, raw = struct.unpack_from("<IIII", data, pos + 12)
            if kind == 2 and data[raw:raw + 4] == b"RSDS":
                if amount < 24 or raw + amount > len(data):
                    raise ValueError("Truncated CodeView RSDS")
                identities.add((data[raw + 4:raw + 20], _u32(data, raw + 20)))
        if len(identities) > 1:
            raise ValueError("Ambiguous CodeView RSDS identities")
        return next(iter(identities), None)
    except struct.error as exc:
        raise ValueError("Truncated PE metadata") from exc


def pdb_identity(data: bytes):
    """Read PDB stream 1 (GUID/Age), not the much larger debug streams."""
    try:
        if data[:32] != b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0":
            raise ValueError("Unsupported PDB format")
        block, _, count, directory_size, _, map_block = struct.unpack_from("<6I", data, 32)
        if block not in (512, 1024, 2048, 4096, 8192, 16384, 32768) or count * block > len(data):
            raise ValueError("Invalid PDB superblock")
        def page(index):
            if index >= count:
                raise ValueError("Invalid PDB page index")
            return data[index * block:(index + 1) * block]
        def pages(size):
            return (size + block - 1) // block
        directory_count = pages(directory_size)
        if map_block >= count or directory_count * 4 > block:
            raise ValueError("Invalid PDB directory map")
        directory = b"".join(page(_u32(data, map_block * block + i * 4))
                             for i in range(directory_count))[:directory_size]
        streams = _u32(directory, 0)
        if streams < 2 or streams > (len(directory) - 4) // 4:
            raise ValueError("Invalid PDB stream directory")
        sizes = struct.unpack_from(f"<{streams}I", directory, 4)
        pos = 4 + 4 * streams + (0 if sizes[0] == 0xffffffff else pages(sizes[0]) * 4)
        if sizes[1] < 28 or sizes[1] == 0xffffffff or pos + pages(sizes[1]) * 4 > len(directory):
            raise ValueError("Invalid PDB info stream")
        info = page(_u32(directory, pos))
        return info[12:28], _u32(info, 8)
    except struct.error as exc:
        raise ValueError("Truncated PDB metadata") from exc


def verify_symbols(binary_names, debug_names, read_binary, read_debug):
    """Each PDB must match one PE in its own directory; DLL symbols are mandatory."""
    binaries = {}
    for names, read in ((binary_names, read_binary), (debug_names, read_debug)):
        for name in names:
            p = PurePosixPath(name)
            if p.suffix.lower() not in (".dll", ".exe"):
                continue
            # EXE symbols remain optional; check their PE identity only if a PDB is present.
            if p.suffix.lower() == ".exe" and not any(
                PurePosixPath(n).parent == p.parent and PurePosixPath(n).suffix.lower() == ".pdb"
                and PurePosixPath(n).stem.lower() == p.stem.lower() for n in debug_names
            ):
                continue
            identity = pe_identity(read(name))
            if identity is None:
                raise ValueError(f"Missing CodeView identity: {name}")
            binaries[name] = identity
    matched = set()
    for name in debug_names:
        p = PurePosixPath(name)
        if p.suffix.lower() != ".pdb":
            continue
        identity = pdb_identity(read_debug(name))
        candidates = [n for n, value in binaries.items() if value == identity
                      and PurePosixPath(n).parent == p.parent]
        if len(candidates) != 1 or candidates[0] in matched:
            raise ValueError(f"Unmatched or duplicate PDB identity: {name}")
        matched.add(candidates[0])
    missing = {n for n in binaries if PurePosixPath(n).suffix.lower() == ".dll"} - matched
    if missing:
        raise ValueError(f"Missing DLL PDB: {sorted(missing)}")


def verify_debug_layout(binary_names, debug_names):
    """Require the same shared-library modules in Release and Debug."""
    def dlls(names, directory):
        return {p.name.casefold() for name in names
                if (p := PurePosixPath(name)).parent.as_posix() == directory
                and p.suffix.lower() == ".dll"}
    release = dlls(binary_names, "bin")
    debug = dlls(debug_names, "debug/bin")
    if release != debug:
        raise ValueError(f"Debug DLL set differs: missing={sorted(release-debug)}, extra={sorted(debug-release)}")
    # FFmpeg's import libraries retain the module name, optionally with a d suffix.
    libs = {PurePosixPath(name).name.casefold() for name in debug_names
            if PurePosixPath(name).parent.as_posix() == "debug/lib"}
    for name in release:
        module = name[:-4].rsplit("-", 1)[0]
        if not ({module + ".lib", module + "d.lib"} & libs):
            raise ValueError(f"Missing Debug import library for {name}")

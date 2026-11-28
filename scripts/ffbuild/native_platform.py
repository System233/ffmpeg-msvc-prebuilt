"""Native Windows architecture and PE/COFF binary verification."""
from __future__ import annotations

import ctypes
import os
import struct
from pathlib import Path

PE_MACHINE = {"x86-windows": 0x14c, "x64-windows": 0x8664,
            "arm-windows": 0x1c4, "arm64-windows": 0xaa64}
NATIVE_RUNTIME_TRIPLETS = frozenset(("x64-windows", "x86-windows"))
VS_PLATFORM = {"x64-windows": "x64", "x86-windows": "Win32",
               "arm-windows": "ARM", "arm64-windows": "ARM64"}


def pe_machine(path: Path) -> int:
    with path.open("rb") as f:
        if f.read(2) != b"MZ":
            raise ValueError(f"Not a PE executable: {path}")
        f.seek(0x3c)
        offset_raw = f.read(4)
        if len(offset_raw) != 4:
            raise ValueError(f"Truncated PE header: {path}")
        offset = struct.unpack("<I", offset_raw)[0]
        f.seek(offset)
        if f.read(4) != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {path}")
        raw = f.read(2)
        if len(raw) != 2:
            raise ValueError(f"Truncated PE machine field: {path}")
        return struct.unpack("<H", raw)[0]


def can_execute(triplet: str) -> bool:
    """Ask Windows about native/guest machine support, never infer from target name alone."""
    if os.name != "nt":
        return False
    machine = PE_MACHINE[triplet]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        native, process = ctypes.c_ushort(), ctypes.c_ushort()
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.IsWow64Process2.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort)]
        kernel.IsWow64Process2.restype = ctypes.c_int
        if not kernel.IsWow64Process2(kernel.GetCurrentProcess(), ctypes.byref(process), ctypes.byref(native)):
            return False
        if machine == native.value:
            return True
        supported = ctypes.c_int()
        kernel.IsWow64GuestMachineSupported.argtypes = [ctypes.c_ushort, ctypes.POINTER(ctypes.c_int)]
        kernel.IsWow64GuestMachineSupported.restype = ctypes.c_int
        return kernel.IsWow64GuestMachineSupported(machine, ctypes.byref(supported)) == 0 and bool(supported.value)
    except AttributeError:
        # Unknown compatibility is not a claim that execution succeeded.
        return False


def coff_archive_machines(path: Path) -> set[int]:
    """Read COFF object/import headers without loading multi-GB static archives."""
    machines = set()
    length = path.stat().st_size
    with path.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise ValueError(f"Invalid COFF library: {path}")
        while stream.tell() < length:
            header = stream.read(60)
            if len(header) != 60 or header[58:] != b"`\n":
                raise ValueError(f"Invalid archive member header: {path}")
            name = header[:16].rstrip()
            size = int(header[48:58])
            start = stream.tell()
            end = start + size
            if size < 0 or end > length:
                raise ValueError(f"Truncated archive member: {path}")
            if name not in (b"/", b"//", b"/SYM64/"):
                if name.startswith(b"#1/"):
                    stream.seek(int(name[3:]), 1)
                if end - stream.tell() < 8:
                    raise ValueError(f"Truncated COFF object: {path}")
                head = stream.read(8)
                # Import-object and anonymous bigobj headers store Machine at +6.
                offset = 6 if head[:4] == b"\0\0\xff\xff" else 0
                machines.add(struct.unpack_from("<H", head, offset)[0])
            stream.seek(end + size % 2)
    if not machines:
        raise ValueError(f"No COFF objects in {path}")
    return machines

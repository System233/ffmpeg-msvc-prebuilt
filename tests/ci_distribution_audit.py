
"""Test-only audit of actual public release ZIPs; no extraction or publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import zipfile
from pathlib import Path, PurePosixPath

import yaml

MACHINES = {"x86-windows": 0x14C, "x64-windows": 0x8664,
            "arm-windows": 0x1C4, "arm64-windows": 0xAA64}
CLI = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe"}
LICENSES = {"LICENSE.txt", "share/ffmpeg/copyright", "share/ffmpeg/sbom.spdx.json"}
DLL = re.compile(r"(avcodec|avdevice|avfilter|avformat|avutil|swresample|swscale|postproc)-\d+\.dll")
CORE = {"avcodec", "avdevice", "avfilter", "avformat", "avutil", "swresample", "swscale"}


def require(condition, message):
    if not condition:
        raise ValueError(str(message))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree(names):
    root = {}
    for name in sorted(names):
        node = root
        for part in name.split("/"):
            node = node.setdefault(part, {})
    def walk(node, prefix=""):
        lines = []
        ordered = sorted(node.items(), key=lambda kv: (not bool(kv[1]), kv[0]))
        for i, (name, children) in enumerate(ordered):
            last = i == len(ordered) - 1
            lines.append(prefix + ("\u2514\u2500\u2500 " if last else "\u251c\u2500\u2500 ") + name + ("/" if children else ""))
            lines.extend(walk(children, prefix + ("    " if last else "\u2502   ")))
        return lines
    return "\n".join(walk(root))


def pe_machine(archive, name):
    with archive.open(name) as stream:
        header = stream.read(64)
        require(len(header) == 64 and header[:2] == b"MZ", (name, "DOS header"))
        offset = struct.unpack_from("<I", header, 0x3C)[0]
        require(64 <= offset <= 1024 * 1024, (name, "PE offset"))
        stream.seek(offset)
        pe = stream.read(6)
        require(len(pe) == 6 and pe[:4] == b"PE\0\0", (name, "PE signature"))
        return struct.unpack_from("<H", pe, 4)[0]


def fields(text):
    # Parse logical lines, including CRLF/continuations.
    text = re.sub(r"\\\r?\n", " ", text)
    result = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9.]*)\s*:\s*(.*)$", line)
        if match:
            key, value = match.groups()
            require(key not in result, ("duplicate .pc field", key))
            result[key] = value.strip()
    return result


def check_sdk(archive, names, prefix, expect_symbols):
    bin_prefix, lib_prefix = prefix + "bin/", prefix + "lib/"
    dlls = {n for n in names if n.startswith(bin_prefix) and n.endswith(".dll")
            and "/" not in n.removeprefix(bin_prefix)}
    modules = set()
    for name in dlls:
        match = DLL.fullmatch(PurePosixPath(name).name)
        require(match, ("unexpected SDK DLL", name))
        modules.add(match.group(1))
    require(CORE <= modules, ("missing core modules", prefix, CORE - modules))
    expected_libs = {lib_prefix + m + ".lib" for m in modules}
    actual_libs = {n for n in names if n.startswith(lib_prefix) and n.endswith(".lib")}
    require(actual_libs == expected_libs, ("import libraries", prefix, actual_libs ^ expected_libs))
    actual_pc = {n for n in names if n.startswith(lib_prefix + "pkgconfig/") and n.endswith(".pc")}
    expected_pc = {lib_prefix + "pkgconfig/lib" + m + ".pc" for m in modules}
    require(actual_pc == expected_pc, ("pkg-config modules", prefix, actual_pc ^ expected_pc))
    for name in actual_pc:
        f = fields(archive.read(name).decode("utf-8"))
        require(not f.get("Libs.private", ""), ("private static dependencies", name))
        require(f.get("Cflags"), ("missing Cflags", name))
        tokens = re.findall(r"(?:^|\s)-l([^\s]+)", f.get("Libs", ""))
        require(tokens and all(lib_prefix + t + ".lib" in names for t in tokens),
                ("invalid public Libs", name, tokens))
        require(PurePosixPath(name).stem.removeprefix("lib") in tokens, ("own library missing", name))
        for key in ("Requires", "Requires.private"):
            for dep in f.get(key, "").split(","):
                if dep.strip():
                    require(dep.strip().split()[0] in {"lib" + m for m in modules},
                            ("external pkg-config dependency", name, dep))
    pdb = {n for n in names if n.startswith(bin_prefix) and n.endswith(".pdb")}
    # Release bin/ excludes debug/bin/; every DLL should have its own PDB in Develop.
    expected_pdb = {n.removesuffix(".dll") + ".pdb" for n in dlls} if expect_symbols else set()
    require(pdb == expected_pdb, ("DLL PDB layout", prefix, pdb ^ expected_pdb))
    return modules


def check_asset(path, asset, record, kind):
    require(path.name == asset["file"], ("asset name", path.name))
    require(path.stat().st_size == asset["size"], ("size", path.name))
    sha = digest(path)
    require("sha256:" + sha == asset["digest"], ("sha256", path.name))
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None, ("CRC", path.name))
        entries = z.namelist()
        names = set(entries)
        require(len(names) == len(entries) == len({n.casefold() for n in names}), ("duplicate entries", path.name))
        require(all(not any(c in n for c in "\\:") and
                    not any(s in ("", ".", "..") for s in n.split("/")) for n in names),
                ("unsafe names", path.name))
        require(LICENSES <= names, ("missing public license evidence", path.name))
        require(all(z.getinfo(n).file_size for n in LICENSES), ("empty license evidence", path.name))
        require(not any(n.split("/")[-1].lower() in
                        {"control", "build_info", "vcpkg_abi_info.txt", "vcpkg.spdx.json"} for n in names),
                ("internal vcpkg metadata", path.name))
        require(all(not n.startswith("share/") or n.startswith("share/ffmpeg/") for n in names),
                ("unexpected share namespace", path.name))
        sbom = json.loads(z.read("share/ffmpeg/sbom.spdx.json"))
        require(sbom["spdxVersion"] == "SPDX-2.3", ("SPDX version", path.name))
        pkgs = sbom["packages"]
        ids = {p["SPDXID"] for p in pkgs}
        require(len(ids) == len(pkgs) == record["compliance"]["package_count"], ("SPDX package count", path.name))
        ids.add(sbom["SPDXID"])
        require(all(r["spdxElementId"] in ids and r["relatedSpdxElement"] in ids
                    for r in sbom["relationships"]), ("dangling SPDX relationship", path.name))
        if record["linkage"] == "static":
            require(kind == "binary" and names == CLI | LICENSES, ("static payload", names))
        else:
            require({n.split("/")[0] for n in names} <= {"bin","lib","include","share","debug","LICENSE.txt"},
                    ("shared roots", path.name))
            require({n for n in names if n.endswith(".exe")} == {"bin/" + n for n in CLI}, ("CLI payload", path.name))
            require("share/ffmpeg/FindFFmpeg.cmake" in names, ("CMake module missing", path.name))
            require(all(any(n.startswith("include/lib" + m + "/") and n.endswith(".h") for n in names)
                        for m in CORE), ("missing core headers", path.name))
            modules = check_sdk(z, names, "", kind == "develop")
            if kind == "develop":
                require(check_sdk(z, names, "debug/", True) == modules, ("debug modules differ", path.name))
            else:
                require(not any(n.startswith("debug/") or n.endswith(".pdb") for n in names), ("debug content in Binary", path.name))
            cmake = z.read("share/ffmpeg/FindFFmpeg.cmake").decode("utf-8")
            for release, debug in re.findall(r'(?m)^\s*FFMPEG_ATTACH_MODULE_DEPS\(\S+\s+"([^"]*)"\s+"([^"]*)"\)', cmake):
                require(not release and not debug, ("CMake private dependencies", path.name))
        pe = [n for n in names if n.endswith((".exe", ".dll"))]
        require(all(pe_machine(z,n) == MACHINES[record["triplet"]] for n in pe), ("PE architecture", path.name))
        return {"file":path.name,"kind":kind,"size":asset["size"],"sha256":sha,
                "entries":len(names),"unpacked_bytes":sum(i.file_size for i in z.infolist()),
                "exe":sum(n.endswith(".exe") for n in names),"dll":sum(n.endswith(".dll") for n in names),
                "lib":sum(n.endswith(".lib") for n in names),"pdb":sum(n.endswith(".pdb") for n in names),
                "pc":sum(n.endswith(".pc") for n in names),"headers":sum(n.startswith("include/") and n.endswith(".h") for n in names),
                "spdx_packages":len(pkgs),"tree":tree(names)}


def audit(root, report_dir):
    metadata = list(root.glob("*.var.yaml"))
    require(len(metadata) == 1, ("metadata files", len(metadata)))
    record = yaml.safe_load(metadata[0].read_text(encoding="utf-8"))
    require(record["package_format"] == 3, "unexpected package format")
    require(record["linkage"] in ("shared", "static"), "unexpected linkage")
    assets = record["assets"]
    require(set(assets) == ({"binary","develop"} if record["linkage"] == "shared" else {"binary"}),
            "unexpected asset kinds")
    rows = [check_asset(root / asset["file"], asset, record, kind)
            for kind, asset in sorted(assets.items())]
    if "develop" in assets:
        with zipfile.ZipFile(root / assets["binary"]["file"]) as binary, zipfile.ZipFile(root / assets["develop"]["file"]) as develop:
            require(set(binary.namelist()) < set(develop.namelist()), "Develop must be a strict superset")
            for i in binary.infolist():
                j = develop.getinfo(i.filename)
                require((i.CRC,i.file_size)==(j.CRC,j.file_size), ("Binary/Develop payload differs", i.filename))
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {k:record[k] for k in ("version","triplet","linkage","license","variant_id","abi_hash","package_format")}
    report["assets"] = rows
    (report_dir/"layout.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines = ["# " + record["variant_id"], ""]
    for row in rows:
        lines += ["## "+row["file"], "",
                  f'{row["entries"]} files; {row["size"]:,} bytes; SHA-256: {row["sha256"]}', "",
                  "\x60\x60\x60text", row["tree"], "\x60\x60\x60", ""]
        print("PASS",row["file"],row["entries"],"files",row["size"],"bytes")
    md = "\n".join(lines)
    (report_dir/"directory-tree.md").write_text(md,encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
            f.write(md+"\n")
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("root",type=Path)
    parser.add_argument("report_dir",type=Path)
    args=parser.parse_args()
    audit(args.root,args.report_dir)

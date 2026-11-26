"""Synthetic ABI inputs for offline tests; never used by production scans."""
import hashlib
import json
from ffbuild.identity import variant_name, archive_name
from ffbuild.native_abi import build_requests
from ffbuild.planner import plan_native

def scan_fixture(**kwargs):
    kwargs.setdefault("release_date", "2026-11-25")
    jobs, blocked = build_requests(**kwargs)
    for job in jobs:
        job["abi_hash"] = hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()
        job["id"] = variant_name(job["version"], 0, job["triplet"], job["linkage"],
                                 job["license"], abi_hash=job["abi_hash"])
    return {"schema": 3, "jobs": jobs, "blocked": blocked}

def plan_fixture(*, state, force=False, **kwargs):
    return plan_native(scan_fixture(**kwargs), state=state, force=force)

def install_abi(package, job, content=b"native ABI"):
    path = package / "share/ffmpeg/vcpkg_abi_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    job["abi_hash"] = hashlib.sha256(content).hexdigest()
    job["id"] = variant_name(job["version"], 0, job["triplet"], job["linkage"],
                             job["license"], abi_hash=job["abi_hash"])

def release_record(job):
    row = dict(job, variant_id=job["id"], channel="master" if job["yaml"] == "master" else "release",
               package_format=3, assets={})
    if row["channel"] == "master":
        row["source_commit"] = job["source_ref"]
    for kind in ("binary", "develop") if job["linkage"] == "shared" else ("binary",):
        row["assets"][kind] = {"file": archive_name(row, develop=kind == "develop"),
                               "size": 100, "digest": "sha256:" + "b"*64}
    return row

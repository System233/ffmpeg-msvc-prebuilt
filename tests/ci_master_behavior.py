"""Read-only evidence replay of the isolated Master CI matrix."""
import json
import os
import tempfile
from pathlib import Path

from ffbuild.autoheal import github, triage
from ffbuild.release_trigger import complete_pr_build


def main():
    repo = github.repository()
    rid = int(os.environ["GITHUB_RUN_ID"])
    attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
    run = github.api(f"repos/{repo}/actions/runs/{rid}")
    assert run["event"] == "push" and run["head_branch"] == "ci/e2e-final-20261125"
    assert run["head_sha"] == os.environ["GITHUB_SHA"] and run["run_attempt"] == attempt
    jobs = github.collection(f"repos/{repo}/actions/runs/{rid}/attempts/{attempt}/jobs", "jobs")
    artifacts = github.collection(f"repos/{repo}/actions/runs/{rid}/artifacts", "artifacts")
    available = triage._artifact_names(artifacts)
    plan = None
    name = f"ffbuild-plan-master-a{attempt}"
    if name in available:
        with tempfile.TemporaryDirectory() as tmp:
            github.download_artifact(rid, name, Path(tmp))
            plan = json.loads((Path(tmp) / "ffbuild-plan.json").read_text(encoding="utf-8"))
        request = plan["request"]
        assert plan["schema"] == 3 and request["production"] is False
        assert request["yaml"] == "master" and request["repository_commit"] == run["head_sha"]
        assert request["plan_attempt"] == attempt
        assert len(plan["jobs"]) == 16 and not plan["reuse"]
        assert len({(j["triplet"], j["package"]) for j in plan["jobs"]}) == 16
    assert triage.production_request(run, plan) is None
    logs = {}
    for job in jobs:
        if job.get("conclusion") not in ("failure", "timed_out"):
            continue
        row = triage._matching_job(job, (plan or {}).get("jobs", []))
        if row:
            artifact = f"build-logs-a{attempt}-{row['yaml']}-{row['id']}"
            if artifact in available:
                logs[artifact] = triage._sample_log(rid, artifact)
    # Exercise pure classification only, not the trusted production gate.
    result = triage.analyze(dict(run, name="Build FFmpeg Master"), attempt, jobs, artifacts, plan, logs=logs)
    result["source"]["run_name"] = run["name"]
    result["source"]["run_conclusion"] = os.environ["MATRIX_RESULT"]
    result["test_only"] = True
    result["trusted_repair_source"] = False
    result["repair_matrix"] = []
    result["would_diagnose_if_trusted"] = [g["yaml"] for g in result["groups"] if g["repairable"]]
    result["full_matrix_passed"] = bool(plan and complete_pr_build("master", plan["jobs"], jobs))
    result["snapshot"] = {k: plan["request"][k] for k in ("ref", "commit", "sha512")} if plan else None
    out = Path("master-behavior")
    out.mkdir()
    triage.write_json(out / "master-behavior.json", result)
    lines = ["# Master isolated native build behavior", "",
             f"Matrix: {os.environ['MATRIX_RESULT']}; full matrix passed: {result['full_matrix_passed']}",
             f"Plan present: {plan is not None}; planned workers: {result['planned_variants']}",
             f"Source snapshot: {result['snapshot']}", "",
             "Classification only; isolated push is NOT a trusted Auto-Heal source.",
             "No Agent, PR, Release or Tag mutation is performed.", "",
             "| Classification | Eligible if trusted | Workers | Signatures |",
             "|---|---|---:|---:|"]
    for group in result["groups"]:
        lines.append(f"| {group['classification']} | {group['repairable']} | {len(group['jobs'])} | {len({j['signature'] for j in group['jobs']})} |")
    for diag in result["diagnostics"]:
        lines.append(f"| {diag['classification']} | False | 1 | - |")
    records = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, name in enumerate(sorted(n for n in available if n.startswith("ffbuild-layout-") and n.endswith(f"-a{attempt}"))):
            folder = Path(tmp) / str(i)
            github.download_artifact(rid, name, folder)
            record = json.loads((folder / "layout.json").read_text(encoding="utf-8"))
            assert plan and record["variant_id"] in {row["id"] for row in plan["jobs"]}
            records.append(record)
    assert len({r["variant_id"] for r in records}) == len(records)
    count = sum(len(r["assets"]) for r in records)
    lines += ["", f"Verified public ZIPs: {count}", "", "| ZIP | Files | Bytes |", "|---|---:|---:|"]
    for record in records:
        for asset in record["assets"]:
            lines.append(f"| {asset['file']} | {asset['entries']} | {asset['size']:,} |")
    summary = "\n".join(lines) + "\n"
    (out / "directory-structures.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    trees = [summary]
    for record in records:
        for asset in record["assets"]:
            trees += ["## " + asset["file"], "", "\x60\x60\x60text", asset["tree"], "\x60\x60\x60", ""]
    (out / "directory-structures.md").write_text("\n".join(trees), encoding="utf-8")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
        f.write(summary)
    print(summary)
    if os.environ["MATRIX_RESULT"] == "success":
        assert result["full_matrix_passed"] and len(records) == 16 and count == 24


if __name__ == "__main__":
    main()

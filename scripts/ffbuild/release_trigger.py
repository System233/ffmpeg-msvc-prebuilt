"""Authenticate version-scoped CI and create immutable release tags.

This module never runs a compiler. The GitHub App writer is used only by
trusted main workflows; PRs have no publication credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

from .identity import date_suffix, utc_release_date
from .autoheal.models import commit_sha, version_name

BOT = "ffmpeg-dev[bot]"
_TAG = re.compile(r"ffmpeg-(master|\d+\.\d+(?:\.\d+)?)-(\d{6})(?:R(?:[2-9]|[1-9][0-9]))?")
_AUTO = re.compile(r"auto/ffmpeg-(\d+\.\d+(?:\.\d+)?)")
_REPAIR = re.compile(r"autoheal/(master|\d+\.\d+(?:\.\d+)?)/[0-9a-f]{16}(?:-r[1-9]\d*)?")


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def parse_tag(tag: str) -> tuple[str, str]:
    match = _TAG.fullmatch(tag)
    if not match:
        raise ValueError("Expected ffmpeg-<version>-YYMMDD publication tag")
    suffix = match[2]
    day = date.fromisoformat(f"20{suffix[:2]}-{suffix[2:4]}-{suffix[4:]}")
    return version_name(match[1]), day.isoformat()


def automatic_pr(pr: dict, repo: str) -> tuple[str, str] | None:
    """Return (target, kind); malformed bot PRs fail closed, humans stay quick."""
    head = pr.get("head") or {}
    branch = head.get("ref", "")
    reserved = branch.startswith(("auto/ffmpeg-", "autoheal/", "fix/ffmpeg-"))
    same_repo = (head.get("repo") or {}).get("full_name", "").lower() == repo.lower()
    bot = (pr.get("user") or {}).get("login") == BOT
    if not bot or not same_repo:
        return None
    labels = [v.get("name", "") for v in pr.get("labels", []) if isinstance(v, dict)]
    version_labels = [v for v in labels if v.startswith("version:")]
    if not reserved and not version_labels:
        return None
    match = _AUTO.fullmatch(branch) or _REPAIR.fullmatch(branch)
    if not match or (pr.get("base") or {}).get("ref") != "main":
        raise ValueError("Invalid automatic version PR branch/base")
    version = version_name(match[1])
    if version_labels != ["version:" + version]:
        raise ValueError("Automatic PR requires exactly one matching version label")
    return version, "new" if _AUTO.fullmatch(branch) else "repair"


def snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"ref", "commit", "sha512"}:
        raise ValueError("Master requires a pinned source snapshot")
    if not re.fullmatch(r"n?\d+\.[A-Za-z0-9.+-]+", value["ref"]):
        raise ValueError("Invalid master describe")
    commit_sha(value["commit"])
    if not re.fullmatch(r"[0-9a-f]{128}", value["sha512"]):
        raise ValueError("Invalid master source SHA512")
    return value


def event() -> dict:
    return json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))


def output(values: dict, github_output: bool) -> None:
    if github_output:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            for k, v in values.items():
                if not isinstance(v, str) or "\n" in v or "\r" in v:
                    raise ValueError("Invalid workflow output")
                f.write(f"{k}={v}\n")
    print(json.dumps(values))


def pr_gate(payload: dict, repo: str) -> dict:
    pr = payload.get("pull_request")
    if not pr:
        return {"version": ""}
    target = automatic_pr(pr, repo)
    if not target:
        return {"version": ""}
    from .autoheal.scope import check_pr
    version, kind = target
    base, head = commit_sha(pr["base"]["sha"]), commit_sha(pr["head"]["sha"])
    # Guard code is loaded from base; check_pr reads candidate blobs from Git,
    # not from the currently checked-out working tree.
    check_pr(version, base, head, Path.cwd(), allow_new=kind == "new")
    return {"version": version}


def prior_source_pin(environ: dict[str, str], version: str) -> dict | None:
    attempt = int(environ.get("GITHUB_RUN_ATTEMPT") or "1")
    if attempt <= 1:
        return None
    from .autoheal import github
    import tempfile
    run_id = int(environ["GITHUB_RUN_ID"])
    artifacts = github.collection(f"repos/{github.repository()}/actions/runs/{run_id}/artifacts", "artifacts")
    matching = []
    for artifact in artifacts:
        match = re.fullmatch(r"ffbuild-source-a([1-9]\d*)", artifact.get("name", ""))
        if match and int(match[1]) < attempt:
            matching.append((int(match[1]), artifact))
    if not matching:
        # No source pin was successfully uploaded in a previous attempt.
        return None
    _, item = max(matching, key=lambda x: x[0])
    if item.get("expired"):
        raise ValueError("Previous source pin expired; start a new explicit build")
    with tempfile.TemporaryDirectory(prefix="ffbuild-source-") as tmp:
        directory = Path(tmp)
        github.download_artifact(run_id, item["name"], directory)
        file = directory / "ffbuild-source.json"
        if not file.is_file() or file.stat().st_size > 4096:
            raise ValueError("Missing prior source pin")
        prior = json.loads(file.read_text(encoding="utf-8"))
    if prior.get("repository_commit") != environ.get("GITHUB_SHA") or prior.get("version") != version or prior.get("production") != "true":
        raise ValueError("Prior source pin differs from dispatch request")
    date_suffix(prior["date"])
    if version == "master":
        snapshot({k: prior[k] for k in ("ref", "commit", "sha512")})
    return {k: prior[k] for k in ("version", "date", "production", "ref", "commit", "sha512")}


def build_gate(payload: dict, environ: dict[str, str]) -> dict:
    ref = environ.get("GITHUB_REF", "")
    requested = environ.get("TARGET_VERSION", "")
    validation = environ.get("VALIDATION_ONLY", "").lower() == "true"
    skip = environ.get("SKIP_PUBLISH", "").lower() == "true"
    history = environ.get("REQUESTED_HISTORY", "").lower() == "true"
    shards = environ.get("REQUESTED_SHARDS", "1") or "1"
    if history:
        raise ValueError("History-wide builds are prohibited")
    event_name = environ.get("GITHUB_EVENT_NAME")
    production = event_name in ("workflow_dispatch", "schedule") and ref == "refs/heads/main"
    if production:
        if (validation or skip or shards != "1" or
                (environ.get("REQUESTED_SHARD_INDEX") or "0") != "0" or
                environ.get("REQUESTED_FORCE", "").lower() == "true" or
                environ.get("SKIP_RELEASE", "").lower() == "true"):
            raise ValueError("Production requires the complete single-version publication scope")
        version = version_name(requested)
        if event_name == "schedule" and version != "master":
            raise ValueError("Only Master may build on a schedule")
        if event_name == "workflow_dispatch" and payload.get("inputs", {}).get("yaml") != version:
            raise ValueError("Dispatch target differs from requested version")
        actual = commit_sha(git("rev-parse", "HEAD"))
        if actual != commit_sha(environ.get("GITHUB_SHA")):
            raise ValueError("Checkout differs from the dispatch source")
        subprocess.run(["git", "merge-base", "--is-ancestor", actual, "origin/main"], check=True)
    elif not validation or not skip:
        raise ValueError("Only explicit main dispatch or scheduled Master may publish")
    if ref.startswith("refs/tags/"):
        raise ValueError("Tag pushes never build FFmpeg")
    if environ.get("GITHUB_EVENT_NAME") == "pull_request":
        pr = payload["pull_request"]
        selected = automatic_pr(pr, environ["GITHUB_REPOSITORY"])
        if not selected or selected[0] != requested or shards != "1":
            raise ValueError("Unauthorized automatic PR build target")
        # Recheck scope against the actual merge candidate, not just the head.
        from .autoheal.scope import check_pr
        base = commit_sha(pr["base"]["sha"])
        check_pr(requested, base, git("rev-parse", "HEAD"), Path.cwd(),
                 allow_new=selected[1] == "new")
    elif (event_name == "push" and ref == "refs/heads/ci/debug-addon-e2e-20261126"
          and requested == "8.1.3" and validation and skip
          and environ.get("REQUESTED_FORCE", "").lower() == "true"
          and environ.get("SKIP_RELEASE", "").lower() != "true"
          and shards == "1"):
        # Temporary CI-only branch entry. Never merge this change into main.
        if payload.get("ref") != ref or commit_sha(git("rev-parse", "HEAD")) != commit_sha(environ.get("GITHUB_SHA")):
            raise ValueError("E2E checkout differs from push")
    elif not production:
        raise ValueError("Unauthorized native build event")
    version = version_name(requested)
    from .versions import versions, has_source
    if version != "master" and (version not in versions() or not has_source(version)):
        raise ValueError("Not a source-backed FFmpeg version")
    if production:
        prior = prior_source_pin(environ, version)
        if prior is not None:
            return prior
    if version == "master":
        if environ.get("GITHUB_EVENT_NAME") == "pull_request":
            pin = master_pr_pin(payload["pull_request"])
        else:
            from .master import master_metadata
            pin = snapshot(master_metadata())
    else:
        pin = {"ref": "", "commit": "", "sha512": ""}
    return {"version": version, "date": utc_release_date(), "production": str(production).lower(), **pin}


def ensure_label(version: str) -> str:
    from .autoheal import github
    name = "version:" + version_name(version)
    # gh label create --force is idempotent for the bot-owned namespace.
    subprocess.run(["gh", "label", "create", name, "--repo", github.repository(),
                    "--color", "1d76db", "--description", "Automatic FFmpeg build target",
                    "--force"], check=True)
    return name


def publication_tag_candidate(version: str, day: str, commit: str, batch: str) -> tuple[str, bool]:
    """Read-only allocation. Reuse only an exact annotated publication batch."""
    version_name(version)
    commit = commit_sha(commit)
    if not re.fullmatch(r"[0-9a-f]{64}", batch):
        raise ValueError("Invalid verified release batch identity")
    stem = f"ffmpeg-{version}-{date_suffix(day)}"
    for number in range(1, 100):
        tag = stem if number == 1 else f"{stem}R{number}"
        ref = f"refs/tags/{tag}"
        remote = git("ls-remote", "origin", ref, ref + "^{}")
        if not remote:
            return tag, False
        lines = dict((r, sha) for sha, r in (line.split() for line in remote.splitlines()))
        if lines.get(ref + "^{}") != commit:
            continue
        git("fetch", "--no-tags", "origin", f"{ref}:{ref}")
        try:
            annotation = json.loads(git("for-each-ref", "--format=%(contents)", ref))
        except ValueError:
            continue
        if isinstance(annotation, dict) and annotation.get("batch") == batch and annotation.get("repository_commit") == commit:
            if "release" in annotation:
                import hashlib
                if hashlib.sha256(json.dumps(annotation["release"], sort_keys=True,
                        separators=(",", ":")).encode("utf-8")).hexdigest() != batch:
                    raise ValueError("Publication tag recovery metadata does not match batch")
            return tag, True
    raise ValueError("Same-day immutable publication tag slots exhausted")


def write_publication_tag(tag: str, commit: str, batch: str, *, release_record: dict | None = None) -> None:
    """Called only by the publisher after all fresh and reused ZIPs pass."""
    parse_tag(tag)
    commit = commit_sha(commit)
    if not re.fullmatch(r"[0-9a-f]{64}", batch):
        raise ValueError("Invalid verified release batch identity")
    if commit != commit_sha(git("rev-parse", "HEAD")):
        raise ValueError("Publication checkout differs from verified build")
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], check=True)
    if not os.environ.get("GH_TOKEN"):
        raise ValueError("GitHub App token required for publication")
    subprocess.run(["gh", "auth", "setup-git"], check=True)
    ref = f"refs/tags/{tag}"
    evidence = {"batch": batch, "repository_commit": commit}
    if release_record is not None:
        import hashlib
        actual = hashlib.sha256(json.dumps(release_record, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        if actual != batch:
            raise ValueError("Release recovery metadata differs from verified batch")
        evidence["release"] = release_record
    annotation = json.dumps(evidence, separators=(",", ":"))
    # A runner retry may retain the local tag after a failed push; never move it.
    if git("tag", "--list", tag):
        if (git("rev-parse", ref + "^{commit}") != commit or
                json.loads(git("for-each-ref", "--format=%(contents)", ref)) != json.loads(annotation)):
            raise ValueError("Local publication tag conflicts")
    else:
        git("-c", "user.name=ffmpeg-dev[bot]", "-c", "user.email=295689149+ffmpeg-dev[bot]@users.noreply.github.com",
            "tag", "-a", tag, commit, "-m", annotation)
    git("push", "origin", f"{ref}:{ref}")


def complete_pr_build(version: str, planned: list[dict], jobs: list[dict]) -> bool:
    from .targets import load_targets
    expected = {(t.triplet, t.package) for t in load_targets()}
    actual = {(row.get("triplet"), row.get("package")) for row in planned}
    if len(planned) != len(expected) or actual != expected or any(row.get("yaml") != version for row in planned):
        return False
    for row in planned:
        suffix = "/ ffbuild-" + row["id"]
        matches = [j for j in jobs if j.get("name", "").endswith(suffix)]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            return False
    return True


def master_pr_pin(pr: dict) -> dict:
    """Reuse the exact upstream source from the initial failed Master run."""
    from .autoheal import github
    base, head = commit_sha(pr["base"]["sha"]), commit_sha(pr["head"]["sha"])
    merge_base = git("merge-base", base, head)
    first = git("rev-list", "--reverse", f"{merge_base}..{head}").splitlines()[0]
    text = git("show", "-s", "--format=%B", first)
    ids = re.findall(r"(?m)^Autoheal-Source-Run: ([1-9]\d*)$", text)
    attempts = re.findall(r"(?m)^Autoheal-Source-Attempt: ([1-9]\d*)$", text)
    if len(ids) != 1 or len(attempts) != 1:
        raise ValueError("Master repair must reference its original failed build attempt")
    from .autoheal.triage import _plan_from_artifact, production_request
    run_id, attempt = int(ids[0]), int(attempts[0])
    run, _, jobs, artifacts = github.run_data(run_id, attempt)
    info = github.api(f"repos/{github.repository()}/actions/runs/{run_id}/attempts/{attempt}")
    plan = _plan_from_artifact(run_id, attempt, artifacts, info["run_started_at"])
    if plan is None and attempt > 1:
        from .run_artifacts import plan_artifact
        selected = plan_artifact(run_id, attempt, artifacts)
        if selected and selected[0] < attempt:
            generation, _, history = selected
            start = next(a["run_started_at"] for n, a, _ in history if n == generation)
            plan = _plan_from_artifact(run_id, generation, artifacts, start)
            if ((plan or {}).get("request") or {}).get("plan_attempt") != generation:
                plan = None
    request = production_request(run, plan)
    if info.get("conclusion") != "failure" or not request or request["yaml"] != "master":
        raise ValueError("Master repair source is not the original failed Master build")
    return snapshot({k: request[k] for k in ("ref", "commit", "sha512")})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("pr-gate", "build-gate"):
        sub.add_parser(command).add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "pr-gate":
        output(pr_gate(event(), os.environ["GITHUB_REPOSITORY"]), args.github_output)
    else:
        result = build_gate(event(), os.environ)
        if result["production"] == "true" and args.github_output:
            Path("ffbuild-source.json").write_text(json.dumps(dict(result, repository_commit=os.environ["GITHUB_SHA"])), encoding="utf-8")
        output(result, args.github_output)


if __name__ == "__main__":
    main()

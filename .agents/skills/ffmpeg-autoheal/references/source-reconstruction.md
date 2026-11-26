# Reconstruct exactly the failed source

## Incident inputs

agent_context.json includes target_yaml, base_sha, workflow_run_id, run_attempt, source_snapshot (the recorded plan request, when available), failed_jobs and diagnostics. Each diagnostic contains the matched build_plan projection, job/variant, artifact, log_directory, failed_steps, phase, classification and signature. Do not infer missing fields from a variant filename. If an older report lacks the needed evidence, decline rather than silently choose current upstream.

Stable: resolve source.ref and source.sha512 using read_spec and the exact target version (expand ${VERSION}). Master: use the actual build_plan.ref (describe), source_ref (full upstream commit), sha512; cross-check source_snapshot.ref/commit/sha512 when present. All Master variants must agree. The repository base_sha is NOT the upstream source commit. Stable plan rows intentionally have empty ref/source_ref/sha512; obtain the stable pin from the resolved YAML. For PRs, compare plan repository_commit/pr_head/pr_base with the checkout and inspect any configuration differences before using the pin.

Generate the baseline Port before editing; use a temporary directory outside the repository:

    python -m ffbuild generate "$TARGET" --output "$SCRATCH/baseline-ports"
    # For Master use the explicit snapshot instead of the preceding command:
    python -m ffbuild generate master --describe "$SOURCE_DESCRIBE" --commit "$SOURCE_COMMIT" --sha512 "$SOURCE_SHA512" --output "$SCRATCH/baseline-ports"

All variables must come from verified context, never literals from log text. The output directory contains ffmpeg-<version with dots replaced by hyphens>, or ffmpeg-master. Inspect portfile.cmake and manifest; the ordered FFMPEG_PATCHES list is authoritative for the generated Port. Cross-check the resolved YAML and copied patch bytes.

## Obtain and verify source

Inspect the actual vcpkg_from_github call and pinned vcpkg source acquisition rules. For the FFmpeg GitHub archive the usual URL is https://github.com/FFmpeg/FFmpeg/archive/<resolved-ref>.tar.gz. Download that archive only, in scratch, and verify the actual SHA512 before extracting. Python example:

    python -c "import hashlib,sys; from pathlib import Path; print(hashlib.sha512(Path(sys.argv[1]).read_bytes()).hexdigest())" "$ARCHIVE"

Compare with the required checksum exactly. Do not recalculate the configured SHA512 to make an unexpected archive acceptable. With Python 3.12+ extract into an empty scratch directory using tarfile's data filter, reject unexpected layout/symlinks or paths escaping scratch, and locate the actual source root. Keep a pristine copy. Never run downloaded code or build scripts for this investigation.

Use upstream Git history for read-only source comparison (e.g. git log -p -- <file>, git log -S <symbol> -- <file>, git show <commit>:<file>). Use the pinned revision, not HEAD, for comparisons. If Git history is shallow, fetch only necessary upstream history in scratch. The archive checksum is authoritative for patch replay; a Git checkout alone is not proof that it matches the downloaded archive.

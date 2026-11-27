# Candidate acceptance and reporting

## Required local evidence

- Reproduce or explain the actual causal diagnostic for every failed variant; identify missing evidence explicitly. For source/patch edits, replay the entire baseline chain up to the error and the entire candidate chain from pristine verified source.
- Regenerate the target Port with the original pin. Check actual options, manifest dependencies, constraints, all target closures, and patch order against baseline. Confirm the change preserves requested capabilities, license, linkage, architecture and upstream identity. New feature names alone are not evidence of correctness.
- Run python -m ffbuild validate. This validates stable configuration/feature graphs and generates stable ports; it does not compile or verify the pinned Master patch series. Explicitly generate Master with the recorded snapshot as described in source-reconstruction.md.
- Run python -m ffbuild autoheal check-worktree under the existing supervisor environment. A nonzero exit or ok=false means the candidate is not accepted. The validator also checks staged changes, so stage only the final authorized paths after reviewing the worktree. Never edit the context or supervisor variables.
- Inspect git diff and git diff --check; leave the authorized candidate in the worktree. The supervisor stages exact paths, rebuilds from clean roots and creates the commit only after verification. If checks fail, correct within scope or restore only your own candidate changes to the original baseline and decline.

## Native verification

Use autoheal build/test/smoke with a representative native package specification.
Prefer GPL or nonfree shared, static for static-only failure groups, and LGPL
only when needed for an LGPL-specific failure. Select an affected architecture.
Write validation-plan.json as {"checks":[{"spec":"ffmpeg[all-gpl]:x64-windows",
"jobs":[123],"reason":"reproduces the same diagnostic"}]}. Every failed job ID
must appear once. Explain cross-architecture grouping using the original logs.

Tester compile/link and PE/COFF inspection apply to all targets. Execute
Tester/CLI and encoding smoke tests only when the host supports the target
machine. A skipped cross-architecture runtime is not a runtime pass.

## Report contract

Write an untracked fix_report.md in English. Successful candidate report:

    Decision: candidate
    Root cause: <concise evidence-based hypothesis>
    Source: <resolved ref/commit and SHA512>
    Failed variants: <job/variant and first causal diagnostic; include log references>
    Repair rationale: <why the correction preserves the required behavior>
    Files changed: <explicit paths>
    Verification: <commands, actual results, full patch replay and feature comparison>
    Remaining: complete remote MSVC CI

The worker extracts Root cause for the repair manifest. It does not interpret Decision: candidate as proof. If no authorized repair exists, leave HEAD and tracked files at base_sha, with no candidate commit, and write:

    Decision: no_safe_fix
    Root cause: <observed blocker or insufficient evidence>
    Investigation: <what was verified and what requires human/shared-system action>

Representative native FFmpeg/Tester builds are allowed and required. No third-party compilation, remote push, PR creation, merge or publication in the Agent. The delivery job independently verifies scope and provenance; a passing candidate must still complete the configured 16-variant native MSVC matrix and Consumer Tester. Packaging/publication gates remain independent. Do not describe any of these as locally passed unless actually executed.

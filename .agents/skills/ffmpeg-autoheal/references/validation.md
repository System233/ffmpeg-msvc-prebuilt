# Candidate acceptance and reporting

## Evidence and validation methods

The [acceptance checklist](../SKILL.md) defines the required outcomes. The methods below explain how to establish evidence; they are not a prescribed execution sequence. Equivalent evidence is acceptable where it establishes the same result, but actual native build and applicable consumer validation remain required.

- Reproduce or explain the actual causal diagnostic for every failed variant; identify missing evidence explicitly. For source/patch edits, establish the baseline patch state up to the error and verify the complete candidate chain from pristine verified source. Ordered replay or equivalent native-build evidence may establish patch applicability; preserve the still-required patch semantics.
- Regenerate the target Port with the original pin. Check actual options, manifest dependencies, constraints, all target closures, and patch order against baseline. Confirm the change preserves requested capabilities, license, linkage, architecture and upstream identity. New feature names alone are not evidence of correctness.
- `python -m ffbuild validate` is available for static recipe validation. This validates stable configuration/feature graphs and generates stable ports; it does not compile or verify the pinned Master patch series. Master validation must use the recorded snapshot, as described in source-reconstruction.md.
- `python -m ffbuild autoheal check-worktree` checks scope under the existing supervisor environment. A nonzero exit or ok=false means the candidate is not accepted. The validator also checks staged changes, so stage only the final authorized paths after reviewing the worktree. Never edit the context or supervisor variables.
- `git diff` and `git diff --check` help verify the exact candidate; leave the authorized candidate in the worktree. The supervisor stages exact paths, rebuilds from clean roots and creates the commit only after verification. If checks fail, correct within scope or restore only your own candidate changes to the original baseline and decline.

## Native verification

Use autoheal build/test/smoke with a representative native package specification.
Prefer GPL or nonfree shared, static for static-only failure groups, and LGPL
only when needed for an LGPL-specific failure. Select an affected architecture; prefer x64 for architecture-independent failures when available. Nonfree requires prepared dependencies. Avoid rebuilding the entire production matrix.
Write validation-plan.json as {"checks":[{"spec":"ffmpeg[all-gpl]:x64-windows",
"jobs":[123],"reason":"reproduces the same diagnostic"}]}. Every failed job ID
must appear once. Explain cross-architecture grouping using the original logs.

Tester compile/link and PE/COFF inspection apply to all targets. Execute
Tester/CLI and encoding smoke tests only when the host supports the target
machine. A skipped cross-architecture runtime is not a runtime pass.

## Report contract

Write an untracked fix_report.md in English. Successful candidate report:

    Decision: candidate
    Title: fix(<target>): <concise concrete English correction>
    Root cause: <concise evidence-based hypothesis>
    Source: <resolved ref/commit and SHA512>
    Failed variants: <job/variant and first causal diagnostic; include log references>
    Repair rationale: <one concise public English paragraph explaining what changed, why it fixes the cause, and why required behavior is preserved>
    Files changed: <explicit paths>
    Verification: <actual commands and results, patch/feature evidence and checklist conclusions>
    Remaining: complete remote MSVC CI

The worker requires Decision, Title (120 characters), Root cause (300 characters) and Repair rationale (1200 characters). Use one nonempty line per field; do not include credentials, private environment information or raw logs. The public native validation summary comes from the separate Verify Runner, not from Agent claims. It does not interpret Decision: candidate as proof. If no authorized repair exists, leave HEAD and tracked files at base_sha, with no candidate commit, and write:

    Decision: no_safe_fix
    Root cause: <observed blocker or insufficient evidence>
    Investigation: <what was verified, unsatisfied acceptance items and their blockers>

Representative native FFmpeg/Tester builds are allowed and required. No third-party compilation, remote push, PR creation, merge or publication in the Agent. The delivery job independently verifies scope and provenance; a passing candidate must still complete the configured 16-variant native MSVC matrix and Consumer Tester. Packaging/publication gates remain independent. Do not describe any of these as locally passed unless actually executed.

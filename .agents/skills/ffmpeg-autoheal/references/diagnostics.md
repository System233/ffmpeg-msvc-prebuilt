# Trace the failure to its first causal error

Inspect all diagnostic entries. Use their artifact and log_directory, not guessed filenames. Search bounded excerpts (rg -n with context, tail, sed) and read the relevant region around the first real failure. Preserve variant, file and line references in the report. A final "BUILD_FAILED" or CMake stack trace is only a summary. Parallel make may interleave unrelated errors; correlate failing command, object, exit code and subsequent errors. A configure probe can fail normally; confirm that the required feature or build actually fails because of it.

| Stage | Investigation |
|---|---|
| Source preparation | Check archive checksum, extraction and ordered patch messages. Network/checksum failure is not a source patch defect. |
| Patch | Inspect ffmpeg/patch-<triplet>-<index>-err.log, matching stdout and ordered generated patch list. A successful application with line offsets is not itself a failure. Reproduce the complete sequence. |
| Configure | Read ffmpeg/build-<triplet>-rel-* and build-<triplet>-dbg-* logs and saved ffbuild/config.log (actual copied filename can differ). Find the final failed required check and exact test source, command, flags, headers and link result. Trace configure dependency expressions and generated options. |
| Compile | Locate the first failing translation unit and compiler invocation. Inspect declaration/definition, conditional macros, type/ABI changes, include order, arch-specific branches and selected dependency API. Distinguish errors from warnings and cascades. |
| Link | Trace the unresolved or duplicated symbol from caller to provider; inspect definitions, export/DEF rules, import vs static library naming, dependency edges, link flags and MSVC calling conventions. Do not suppress unresolved symbols. |
| Consumer | Read ffmpeg-tester logs. Trace the installed public header, export or package-discovery contract back to FFmpeg source/configuration. Do not modify the tester. |
| Outside scope | Dependency build, environment, cache, timeout, ABI mismatch, packaging, compliance or publishing failures require their own evidence. Do not manufacture an FFmpeg patch to solve them. |

Compare release and debug, static and shared, LGPL and GPL, and architectures. Determine whether each failure has the same cause before grouping it. A common signature is a routing key, not proof. Where useful inspect prior working source/configuration using git diff and git show, and check upstream changes at the pinned commit. Establish what changed and why the proposed fix addresses it. If evidence is missing, state which observation is needed; do not assert an unverified API or behavior.

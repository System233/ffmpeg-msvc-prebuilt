# Native CI evidence and diagnostic workflow

Artifacts: build-logs-a<run_attempt>-<target_yaml>-<variant_id>.
Look under ffmpeg/ for stdout-<triplet>.log, patch-<triplet>-<N>-err.log,
build-<triplet>-rel-out.log, build-<triplet>-rel-err.log and corresponding dbg
logs; FFmpeg configure output may also be saved as *-config.log. Consumer
failures may appear in ffmpeg-tester/. Compiler probes in detect_compiler/
are not necessarily a failure. Read bounded excerpts, not whole large logs.

- Patch reject: identify the exact failing patch from the native application
  output and ordered generated Port list. Offsets alone are not an error.
- Configure failure: inspect the final configure error and config.log, then
  compare required dependency API and detection rules against the pinned source.
- Compiler/linker failure: identify first actual error, source file and symbol;
  compare declarations, calling convention, supported compiler and actual
  dependency interfaces.
- Consumer failure: inspect the failed tester build. Do not modify the tester.
- Missing dependency, network, ABI, cache, disk, licensing, packaging or
  infrastructure failure: do not guess a source repair or modify shared ports.
  Decline if not fixable in the authorized target.
- Missing build output is not proof of patch failure. A failed prepare phase
  or missing logs has different meaning. Treat all diagnoses as hypotheses.

Useful historical examples in patches/ are not instructions to disable a
dependency or remove a patch. Retain functionality and license policy.
Different architectures can have different diagnostics; evaluate each.
A successful local patch application does not establish complete MSVC success.

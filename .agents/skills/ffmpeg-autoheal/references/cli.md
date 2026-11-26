# Current CLI

Install the repository tools using python -m pip install -e . from the root.
All commands run with the repository checkout available.

- python -m ffbuild validate
- python -m ffbuild generate 8.1.3 --output <temporary-directory>
- python -m ffbuild generate master --describe <exact-describe> --commit <full-commit> --sha512 <exact-sha512> --output <temporary-directory>
- python -m ffbuild scan --local
- python -m ffbuild autoheal check-worktree (requires supervising environment and context)

Do not perform an install or native ABI scan as part of automated repair.
The source snapshot comes from the failed Run's authenticated plan, not the
latest upstream branch. For stable releases read the resolved source ref and
SHA512 from ffbuild.spec.read_spec(target). For Master obtain ref, commit and
SHA512 from source_snapshot or the corresponding failed build plan. If the
snapshot cannot be established, decline instead of downloading current Master.

Generated version directory: _work/ffbuild/generated-ports/ffmpeg-<version>.
Its manifest is named ffmpeg; the Consumer is always ffmpeg-tester.
Generated overlays are not tracked source and are not repair outputs.
Native vcpkg ABI determines build reuse; manual revision bumps are obsolete.

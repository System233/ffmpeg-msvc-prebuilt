# Reconstruct and repair an ordered patch series

Never modify an existing tracked patch. Work with the exact checksum-verified source and generated baseline Port in scratch.

1. Inspect the ordered FFMPEG_PATCHES list in portfile.cmake. Generated filenames have zero-based order prefixes; map each back to the effective YAML entry by index, not by basename alone. The vcpkg patch log index is also zero-based.
2. Inspect the pinned vcpkg scripts/cmake/z_vcpkg_apply_patches.cmake for the exact application flags. At the current baseline it uses Git with core.longpaths=true, core.autocrlf=false, core.filemode=true, GIT_CONFIG_NOSYSTEM=1, --ignore-whitespace --whitespace=nowarn --verbose. Use the pinned implementation as authority if it changes. Initialize a scratch Git repository inside the pristine extracted tree, with a local author, no CRLF conversion, and commit the pristine input. Never initialize or reset the project repository for this replay.
3. Apply each patch in order, checking before application. For example, from the scratch source root with an absolute patch filename:

       GIT_CONFIG_NOSYSTEM=1 git -c core.longpaths=true -c core.autocrlf=false -c core.filemode=true apply --check --ignore-whitespace --whitespace=nowarn --verbose "$PATCH"
       GIT_CONFIG_NOSYSTEM=1 git -c core.longpaths=true -c core.autocrlf=false -c core.filemode=true apply --ignore-whitespace --whitespace=nowarn --verbose "$PATCH"

   Do not continue after a failed check; do not use --reject, --3way or partial application as proof of native success. Verify the failure matches the real CI diagnostic. Preserve the state after all preceding patches.
4. Read the entire failing patch and identify the intent of every affected hunk. Compare the pre-image, current upstream source, and original intended post-image. Identify changes already upstream, changed context, or API differences; preserve all still-required effects, not only the failing hunk. When the old patch is wholly redundant, removal of its target reference requires evidence of equivalent upstream behavior.
5. Commit the pre-image (pristine + preceding patches) in scratch. Implement the intended post-image on that state. Inspect git diff and git diff --check; stage only intended source changes and use git diff --cached --binary to generate the new patch. Include no earlier patch changes, unrelated files, generated build output or newline churn. A newly needed compatibility patch may also be inserted at the appropriate point; choose its pre-image accordingly. Write a unique descriptive new patch filename under the target major directory. Replace/add the target YAML reference at the intended position. Existing files remain untouched.
6. Regenerate the candidate Port with the same pinned source. From another clean copy of the verified archive, replay the *entire* candidate sequence using the native flags. Confirm later patches still apply and inspect the final affected code. Compare final source semantics and required features; success of git apply is necessary, not sufficient. For multiple failures, repeat diagnosis in the correct sequence state.

For an ordinary configure or compiler repair after the existing patch chain, first replay that chain, then use the resulting state as the new patch pre-image. Report the source checksum, ordered replay count, failure reproduction and final verification.

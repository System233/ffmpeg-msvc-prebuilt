# Reproduce an ordered patch failure without building

Use a temporary source tree outside tracked repository files. Obtain the exact
source archive identified in the failed plan (stable tag or full Master commit)
and verify its SHA512 before extraction. Do not substitute latest upstream.
Inspect the complete ordered patch list using the resolved target YAML or
generated Port. The generated filenames have an application-order prefix.

Apply preceding patches in their exact order using git apply with the same
whitespace policy as native vcpkg. Check each patch with git apply --check
before actually applying it. Stop at the first failure. Diagnose the upstream
context and original patch intent before making a replacement. Do not use
partial rejects as proof of correctness. Recreate a clean temporary source
tree and check the complete new patch sequence before submitting.

If upstream already implements the required behavior, removing the obsolete
reference from the target YAML can be valid only with evidence. Otherwise
add a new target-exclusive patch, preserving the original behavior. Do not
edit existing patch files; select a unique descriptive name under the target
major directory and replace its reference at the appropriate order position.
Confirm that all other existing configurations remain unchanged using
ffbuild autoheal check-worktree. Actual compile/link/consumer validation is
owned by full MSVC CI.

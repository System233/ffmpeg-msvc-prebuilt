#!/bin/sh
# Only a test source package. Executed by the real generated build.sh.
set -eu
printf '%s\n' "$@" > configure.args
printf '%s\n' "$CFLAGS" > configure.cflags
if [ "${FIXTURE_FAIL_STAGE:-}" = configure ]; then
    echo "fixture configure failure" >&2
    exit 41
fi
prefix=""
for arg in "$@"; do
    case "$arg" in
        --prefix=*) prefix="${arg#--prefix=}" ;;
    esac
done
test -n "$prefix"
# GNU make sees the actual install prefix received from build.sh.
printf 'PREFIX := %s\n' "$prefix" > Makefile
cat >> Makefile <<'EOF'
.PHONY: all install
all:
	@test "$$FIXTURE_FAIL_STAGE" != build || { echo "fixture make failure" >&2; exit 42; }
	@printf 'made\n' > make.marker
install: all
	@test "$$FIXTURE_FAIL_STAGE" != install || { echo "fixture install failure" >&2; exit 43; }
	@mkdir -p "$(PREFIX)"
	@printf 'installed\n' > "$(PREFIX)/fixture-install.marker"
EOF

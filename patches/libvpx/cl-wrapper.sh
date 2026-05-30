#!/bin/bash
# Wrapper for MSVC cl.exe that translates GCC-style flags
# This is needed because libvpx's configure script uses -c -o -Werror etc.

ARGS=()
LINK_MODE=false
OUTPUT_FILE=""

for arg in "$@"; do
    case "$arg" in
        -c)
            ARGS+=("/c")
            ;;
        -o)
            # Next arg is the output file
            LINK_MODE=true
            ;;
        -Werror)
            ARGS+=("/WX")
            ;;
        -W*)
            # Ignore other -W flags that MSVC doesn't support
            ;;
        -O0|-O1|-O2|-O3|-Os)
            # Convert -O flags to MSVC format
            ARGS+=("/${arg#-}")
            ;;
        -g*)
            # Ignore -g flags (debug info)
            ARGS+=("/Zi")
            ;;
        -DNDEBUG)
            ARGS+=("-DNDEBUG")
            ;;
        -D*)
            ARGS+=("${arg}")
            ;;
        -I*)
            ARGS+=("${arg}")
            ;;
        *.c|*.cc|*.cpp|*.cxx)
            ARGS+=("${arg}")
            ;;
        *)
            if $LINK_MODE; then
                # This is the output file from -o
                if [[ "$arg" == *.o ]]; then
                    ARGS+=("/Fe${arg%.o}.exe")
                elif [[ "$arg" == *.exe ]]; then
                    ARGS+=("/Fe${arg}")
                else
                    ARGS+=("/Fe${arg}")
                fi
                LINK_MODE=false
            else
                ARGS+=("${arg}")
            fi
            ;;
    esac
done

# If we have -c (compile only), ensure /Fo is set
HAS_Fo=false
HAS_Fe=false
for arg in "${ARGS[@]}"; do
    if [[ "$arg" == /Fo* ]]; then
        HAS_Fo=true
    fi
    if [[ "$arg" == /Fe* ]]; then
        HAS_Fe=true
    fi
done

if [[ " ${ARGS[*]} " == *" /c "* ]]; then
    if ! $HAS_Fo && ! $HAS_Fe; then
        # Default object output
        ARGS+=("/Fo${TMP_O:-a.obj}")
    fi
fi

exec cl.exe "${ARGS[@]}"

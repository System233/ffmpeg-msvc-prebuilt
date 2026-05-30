#!/bin/bash
# Wrapper that translates GCC-style compiler flags to MSVC
# Used by libvpx configure which hardcodes -c -o flags
#
# The libvpx configure's check_cc runs: cl [CFLAGS] "$@" -c -o TMP_O TMP_C
# We need to translate: -c -> /c, -o FILE -> /FoFILE (compile) or /FeFILE (link)

ARGS=()
MODE="compile"
OUTPUT_SET=false

for arg in "$@"; do
    case "$arg" in
        -c)
            ARGS+=("/c")
            ;;
        -o)
            # Next arg is output file - handled in next iteration
            MODE="output"
            ;;
        -E)
            ARGS+=("/E")
            ;;
        -Werror)
            ARGS+=("/WX")
            ;;
        -O0|-O1|-O2|-O3|-Os|-Ofast)
            ARGS+=("/O2")
            ;;
        -g|-g0|-g1|-g2|-g3|-ggdb)
            # Skip -g flags
            ;;
        -m64|-m32)
            # Skip arch flags
            ;;
        -f*|-pedantic*|-W*|-w)
            # Skip GCC-specific flags
            ;;
        -D*|-I*|-U*)
            ARGS+=("${arg}")
            ;;
        -std=*)
            # Skip C standard flags
            ;;
        -MMD|-MP|-MF|-MT|-MQ)
            # Skip dependency flags
            ;;
        *.c|*.cc|*.cpp|*.cxx)
            ARGS+=("${arg}")
            ;;
        *)
            if [ "$MODE" = "output" ]; then
                # This is the -o output file
                local ext="${arg##*.}"
                local base="${arg%.*}"
                if [ "$ext" = "o" ] || [ "$ext" = "obj" ]; then
                    ARGS+=("/Fo${base}.obj")
                elif [ "$ext" = "exe" ]; then
                    ARGS+=("/Fe${arg}")
                else
                    ARGS+=("/Fe${arg}")
                fi
                MODE="compile"
                OUTPUT_SET=true
            else
                ARGS+=("${arg}")
            fi
            ;;
    esac
done

# If we compiled but no /Fo set, add default
if ! $OUTPUT_SET; then
    if [[ " ${ARGS[*]} " == *" /c "* ]]; then
        ARGS+=("/Foa.obj")
    fi
fi

exec cl.exe -nologo "${ARGS[@]}"

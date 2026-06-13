"""
Inject correct ffnvcodec version per FFmpeg major version.

FFmpeg 6.x and earlier use ffnvcodec < 13.0 (11.x).
FFmpeg 7.x+ can use registry baseline (12.x+).
"""

def post_deps(deps, ctx):
    major = ctx["major"]
    if major <= 6:
        deps.append({"name": "ffnvcodec-11"})
    else:
        deps.append({"name": "ffnvcodec"})

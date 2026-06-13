def post_extract(features, ctx):
    """
    Remove avresample feature (FFmpeg >= 5.0).

    avresample was fully removed from FFmpeg 5.0+ serverside.
    Vcpkg ports for 4.x correctly include it; 5.x+ should not.
    """
    if ctx["major"] >= 5 and "avresample" in features:
        del features["avresample"]

"""Add platform-specific features to every Windows-target build."""

_WINDOWS_FEATURES = {
    "w32threads":      "Windows thread support",
    "d3d11va":         "Direct3D 11 Video Acceleration",
    "dxva2":           "DXVA2 hardware decoding",
    "mediafoundation":  "Media Foundation support",
}


def post_extract(features, ctx):
    features.update({k: {"description": v} for k, v in _WINDOWS_FEATURES.items()})
    # d3d12va introduced in FFmpeg 7.0
    if ctx["major"] >= 7:
        features["d3d12va"] = {"description": "Direct3D 12 Video Acceleration"}

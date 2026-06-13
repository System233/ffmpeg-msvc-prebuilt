"""Rename qsv → mfx for pre-8.0 FFmpeg (libvpl replaced libmfx in 8.0)."""

def post_extract(features, ctx):
    if ctx["major"] < 8 and "qsv" in features:
        features["mfx"] = features.pop("qsv")
        features["mfx"]["description"] = "Intel QSV via libmfx (pre-8.0)"

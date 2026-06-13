"""
Inject correct debug/optimization flags per FFmpeg major version.

--enable-debug: adds debug symbols (base OPTIONS, pre-8.x)
--debug: triggers debug_configure (library naming with 'd' suffix, OPTIONS_DEBUG)
"""


def post_options(opts, ctx):
    major, minor = ctx["major"], ctx["minor"]

    if major >= 8:
        opts["base"] = ""
        opts["debug"] = "--disable-optimizations --enable-debug"
    elif major >= 7 or (major == 6 and minor >= 1):  # 6.1+ ~ 7.x
        opts["base"] = "--enable-debug"
        opts["debug"] = "--disable-optimizations"
    elif major >= 5:                                   # 5.1 ~ 6.0
        opts["base"] = "--enable-debug"
        opts["debug"] = "--debug --disable-optimizations"
    elif major >= 4:                                   # 4.2 ~ 5.0.x
        opts["base"] = "--enable-debug"
        opts["debug"] = "--debug"
    else:                                               # 3.x ~ 4.1
        opts["base"] = "--enable-debug"
        opts["debug"] = ""

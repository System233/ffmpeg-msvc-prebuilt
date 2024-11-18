@echo off

SET PATH="%ORIGINAL_PATH%;%MSYSTEM_PREFIX%\bin"
SET MESON_CMD=python3 -m meson
CD /D "%BUILD_DIR%"
%MESON_CMD% setup "%SRC_DIR%" --vsenv  --prefix "%INSTALL_PREFIX%" %*&&%MESON_CMD% compile -C .&&%MESON_CMD% install -C .
EXIT %ERRORLEVEL%
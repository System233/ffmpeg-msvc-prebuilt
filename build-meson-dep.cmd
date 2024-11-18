@echo off

SET PATH="%ORIGINAL_PATH%;%MSYSTEM_PREFIX%\bin"
CD /D "%BUILD_DIR%"
meson setup "%SRC_DIR%" --vsenv  --prefix "%INSTALL_PREFIX%" %*&&meson compile -C .&&meson install -C .
EXIT %ERRORLEVEL%
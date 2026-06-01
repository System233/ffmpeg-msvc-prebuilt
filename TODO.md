# FFmpeg External Library Integration TODO

当前已集成：zlib, x264, fribidi, freetype, harfbuzz, libass, libjxl, x265, libvpx, dav1d, opus, soxr, sdl2, libwebp, nvcodec-headers

## 第一梯队 — 高价值，CMake构建，无复杂依赖

| 库 | FFmpeg flag | 构建 | LICENSE | 状态 | 备注 |
|---|---|---|---|---|---|
| libsrt | `--enable-libsrt` | CMake | MPL 2.0 | 🔨 进行中 | SRT流媒体协议 |
| libxml2 | `--enable-libxml2` | CMake | MIT | 🔨 进行中 | DASH/IMF解封装 |
| libsvtav1 | `--enable-libsvtav1` | CMake | BSD | 🔨 进行中 | 高性能AV1编码 |
| libaom | `--enable-libaom` | CMake | BSD | 📋 待集成 | AV1参考实现，需Perl，aom.pc需手动生成 |
| libmp3lame | `--enable-libmp3lame` | NMake | LGPL | 📋 待集成 | MP3编码，需nmake+Makefile.MSVC |
| libvmaf | `--enable-libvmaf` | Meson | BSD-Patent | ⚠️ 受阻 | MSVC PR未合入 |
| libopenjpeg | `--enable-libopenjpeg` | CMake | BSD | 📋 待集成 | JPEG 2000编解码 |
| openssl | `--enable-openssl` | CMake | Apache 2.0 | 📋 待集成 | TLS/SSL HTTPS协议支持 |
| libsnappy | `--enable-libsnappy` | CMake | BSD | 📋 待集成 | HAP压缩，CMake原生支持 |
| libcodec2 | `--enable-libcodec2` | CMake | LGPL | 📋 待集成 | 低码率语音编解码 |
| libvvenc | `--enable-libvvenc` | CMake | BSD | 📋 待集成 | VVC/H.266编码 |
| liblc3 | `--enable-liblc3` | CMake | Apache 2.0 | 📋 待集成 | LC3音频(BLE) |
| libzmq | `--enable-libzmq` | CMake | MPL 2.0 | 📋 待集成 | ZeroMQ消息传输 |
| librabbitmq | `--enable-librabbitmq` | CMake | MIT | 📋 待集成 | RabbitMQ消息队列 |
| libssh | `--enable-libssh` | CMake | LGPL | 📋 待集成 | SFTP/SCP协议 |
| libgme | `--enable-libgme` | CMake | LGPL | 📋 待集成 | 游戏音乐模拟器(GBS/NSF/VGM) |
| chromaprint | `--enable-chromaprint` | CMake | LGPL | 📋 待集成 | 音频指纹 |

## 第二梯队 — 实用性强，构建中等复杂度

| 库 | FFmpeg flag | 构建 | LICENSE | 状态 | 备注 |
|---|---|---|---|---|---|
| libvorbis | `--enable-libvorbis` | autotools | BSD | 📋 待集成 | Ogg Vorbis编解码，需libogg |
| libogg | — | autotools | BSD | 📋 待集成 | Ogg容器，vorbis/theora/flac前置 |
| libtheora | `--enable-libtheora` | autotools | BSD | 📋 待集成 | Theora视频编解码 |
| libspeex | `--enable-libspeex` | autotools | BSD | 📋 待集成 | Speex窄带音频 |
| libzimg | `--enable-libzimg` | autotools | WTFPL | 📋 待集成 | zscale高质量缩放滤镜 |
| libbluray | `--enable-libbluray` | autotools | LGPL | 📋 待集成 | 蓝光光盘读取 |
| libzvbi | `--enable-libzvbi` | autotools | LGPL | 📋 待集成 | 图文电视/隐藏字幕 |
| libbs2b | `--enable-libbs2b` | autotools | MIT | 📋 待集成 | 交叉馈送DSP音效 |
| libgsm | `--enable-libgsm` | autotools | MIT | 📋 待集成 | GSM全速率音频 |
| libshine | `--enable-libshine` | autotools | LGPL | 📋 待集成 | 定点MP3编码器 |
| libtwolame | `--enable-libtwolame` | autotools | LGPL | 📋 待集成 | MP2音频编码 |
| libilbc | `--enable-libilbc` | autotools | BSD | 📋 待集成 | iLBC语音编解码 |
| libmodplug | `--enable-libmodplug` | autotools | Public Domain | 📋 待集成 | ModPlug模块音乐 |
| libopenmpt | `--enable-libopenmpt` | autotools | BSD | 📋 待集成 | 追踪文件解码(IT/XM/MOD) |
| libcdio | `--enable-libcdio` | autotools | GPL | 📋 待集成 | CD音频抓取 |
| libplacebo | `--enable-libplacebo` | Meson | LGPL | 📋 待集成 | GPU图像处理，需Vulkan |
| librist | `--enable-librist` | Meson | BSD | 📋 待集成 | RIST协议 |
| librubberband | `--enable-librubberband` | Meson | GPL | 📋 待集成 | 音频时间拉伸/音高变换 |
| libfontconfig | `--enable-libfontconfig` | autotools | MIT | 📋 待集成 | 字体配置(drawtext滤镜) |
| libxavs2 | `--enable-libxavs2` | CMake | GPL | 📋 待集成 | AVS2视频编码 |
| libdavs2 | `--enable-libdavs2` | CMake | GPL | 📋 待集成 | AVS2视频解码 |
| libkvazaar | `--enable-libkvazaar` | autotools | BSD | 📋 待集成 | HEVC编码 |
| libvidstab | `--enable-libvidstab` | CMake | GPL | 📋 待集成 | 视频稳像滤镜 |
| libmysofa | `--enable-libmysofa` | CMake | BSD | 📋 待集成 | SOFA HRTF空间音频 |
| libflite | `--enable-libflite` | autotools | BSD | 📋 待集成 | CMU Flite语音合成 |
| libcaca | `--enable-libcaca` | autotools | GPL | 📋 待集成 | ASCII艺术输出滤镜 |
| frei0r | `--enable-frei0r` | autotools | GPL | 📋 待集成 | 视频效果插件 |

## 第三梯队 — 硬件加速/平台特定

| 库 | FFmpeg flag | 构建 | LICENSE | 状态 | 备注 |
|---|---|---|---|---|---|
| AMF | `--enable-amf` | SDK | MIT | 📋 待集成 | AMD Advanced Media Framework |
| CUDA | `--enable-cuda-nvcc` | SDK | NVIDIA | 📋 待集成 | NVIDIA CUDA，需CUDA Toolkit |
| CUVID | `--enable-cuvid` | SDK | NVIDIA | 📋 待集成 | NVIDIA CUVID解码 |
| NVENC | `--enable-nvenc` | SDK | NVIDIA | 📋 待集成 | NVIDIA NVENC编码 |
| D3D12VA | `--enable-d3d12va` | SDK | Microsoft | 📋 待集成 | Direct3D 12 Video Acceleration |
| DXVA2 | `--enable-dxva2` | SDK | Microsoft | 📋 待集成 | DirectX Video Acceleration 2 |
| MediaFoundation | `--enable-mf` | SDK | Microsoft | 📋 待集成 | Windows Media Foundation |
| Vulkan | `--enable-vulkan` | SDK | Khronos | 📋 待集成 | Vulkan GPU计算/解码 |
| OpenCL | `--enable-opencl` | SDK | Khronos | 📋 待集成 | OpenCL GPU计算 |
| libmfx | `--enable-libmfx` | SDK | Intel | 📋 待集成 | Intel Media SDK/QSV(旧API) |
| libvpl | `--enable-libvpl` | CMake | Intel | 📋 待集成 | Intel oneVPL(新API) |
| VAAPI | `--enable-vaapi` | SDK | Linux | ❌ 不适用 | Linux专有 |
| VDPAU | `--enable-vdpau` | SDK | Linux | ❌ 不适用 | Linux专有 |
| VideoToolbox | `--enable-videotoolbox` | SDK | Apple | ❌ 不适用 | macOS/iOS专有 |
| MediaCodec | `--enable-mediacodec` | SDK | Android | ❌ 不适用 | Android专有 |
| MMAL | `--enable-mmal` | SDK | Broadcom | ❌ 不适用 | Raspberry Pi专有 |
| OMX | `--enable-omx` | SDK | Various | ❌ 不适用 | OpenMAX IL嵌入式平台 |

## 许可证敏感 (需 `--enable-nonfree`)

| 库 | FFmpeg flag | 构建 | LICENSE | 状态 | 备注 |
|---|---|---|---|---|---|
| libfdk-aac | `--enable-libfdk-aac` | autotools | nonfree | ❌ 未计划 | AAC编码，许可证与GPL不兼容 |
| decklink | `--enable-decklink` | SDK | nonfree | ❌ 未计划 | Blackmagic DeckLink采集卡 |
| libndi-newtek | `--enable-libndi-newtek` | SDK | nonfree | ❌ 未计划 | NDI网络视频 |
| libxavs | `--enable-libxavs` | autotools | nonfree | ❌ 未计划 | AVS1编码(中国标准) |
| libfaac | `--enable-libfaac` | autotools | nonfree | ❌ 未计划 | AAC编码(已过时) |
| libopencv | `--enable-libopencv` | CMake | nonfree | ❌ 未计划 | OpenCV计算机视觉，非自由许可证 |

## FFmpeg 内置 (无需外部项目)

以下功能由 FFmpeg 自带源码支持，不依赖外部库，仅用于参考：

| 模块 | 说明 |
|---|---|
| libavcodec/aac | 内置AAC编码器(LGPL) |
| libavfilter/af_loudnorm | EBU R128响度标准化 |
| libavfilter/vf_drawtext | 内置文本渲染(依赖freetype) |
| libavformat/hls | HLS muxer/demuxer |
| libavformat/dash | DASH muxer |
| libavcodec/libfdk-aac2 | FFmpeg 7.1+实验性内置AAC |

## 图例

| 符号 | 含义 |
|---|---|
| 🔨 进行中 | 正在集成 |
| 📋 待集成 | 已规划，等待开始 |
| ⚠️ 受阻 | 被上游/MSVC兼容性阻塞 |
| ❌ 未计划 | 暂不集成 |
| ❌ 不适用 | 平台不支持 |
| ✅ 已集成 | 已完成 |

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-05-31 | 初始版本；第一梯队 libsrt/libxml2/libsvtav1 开始集成 |

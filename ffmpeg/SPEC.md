# FFmpeg YAML Port 管理系统规格

## 概述
基于 YAML 的 FFmpeg vcpkg port 生成系统。通过继承机制管理不同版本的 feature、补丁和构建参数，避免重复配置。

## 目录结构
```
ffmpeg/
  base.yaml           # Feature 注册表 + 别名定义 (永不修改)
  5.1.yaml            # 族配置 (extends base, feature 选择, 构建参数)
  5.1.2.yaml          # 版本配置 (extends 5.1, SHA512, 补丁)
  6.1.yaml
  6.1.1.yaml
  ...
  SPEC.md             # 本文件
scripts/
  generate.py         # YAML → port 生成脚本
```

## 设计原则
1. **base 不变**: 新 feature 只追加，不修改已有条目，避免版本间冲突
2. **继承链**: 版本 YAML extends 族 YAML extends base，同大版本继承
3. **声明式**: feature 选择通过 include/exclude/defaults 声明
4. **版本级补丁**: patch 列表定义在具体版本 YAML 中，族 YAML 不包含

## YAML 字段参考

### base.yaml
| 字段 | 类型 | 说明 |
|------|------|------|
| features | map | feature 注册表，key=feature名 |
| features.\<name\>.flag | string | FFmpeg configure --enable-* 标志 |
| features.\<name\>.description | string | 功能描述 |
| features.\<name\>.pkgconfig | string | (核心库) pkg-config 模块名 |
| features.\<name\>.license | string | 许可证约束: gpl / nonfree |
| define | map | 别名定义，value 为 feature 名列表 |

### 族 YAML (X.Y.yaml)
| 字段 | 类型 | 说明 |
|------|------|------|
| extends | string | 继承目标 (base 或 X.Y) |
| source | map | 下载源 |
| source.method | string | git / url |
| source.repo | string | GitHub repo (method=git 时) |
| source.ref | string | 版本引用, `${VERSION}` 占位 |
| build | map | 构建参数 |
| build.base_options | string | 基础 configure 选项 |
| build.debug | map | debug 模式 |
| build.debug.options | string | debug configure 选项 |
| build.release | map | release 模式 |
| build.release.options | string | release configure 选项 |
| build.host_deps | list | host 依赖 (name, host:true) |
| features | map | feature 选择 |
| features.include | list | 启用的 feature |
| features.exclude | list | 禁用的 feature (支持 fnmatch 通配符) |
| features.defaults | list | 默认启用的 feature |

### 版本 YAML (X.Y.Z.yaml)
| 字段 | 类型 | 说明 |
|------|------|------|
| extends | string | 继承目标族 YAML |
| source.sha512 | string | 源码 SHA512 (128 hex) |
| patches | list | 补丁文件名列表 |

## 继承解析
1. 从 base.yaml 开始，沿 extends 链加载
2. features: 子级 include **追加**到父级, exclude **追加**到父级
3. exclude 优先于 include (同名 feature 被 exclude 排除)
4. 通配符: exclude 支持 fnmatch (如 `"post*"` 匹配 postproc)
5. build: 子级字段覆盖父级同名字段
6. patches: 版本 YAML 完全替换 (族 YAML 不定义 patches)

## 别名 (@alias)
`define` 块中定义别名，在 `include/exclude/defaults` 中用 `@name` 引用:
```yaml
define:
  core: [avcodec, avdevice, avformat, avfilter, swresample, swscale]
  all-lgpl: ["@core", zlib, bzip2, ...]
```

循环引用安全：alias 引用其他 alias 时递归展开。

## 生成流程
```
generate.py --version 8.1.1
  ├─ resolve_chain: base → 8.0 → 8.1 → 8.1.1
  ├─ merge_features: include 展开 @alias → 合并 → exclude → fnmatch
  ├─ get_source: 取链中最后的 sha512
  ├─ get_build: 合并链中 build 字段
  ├─ get_patches: 取版本 YAML 的 patches
  ├─ generate_portfile: FFMPEG_VERSION/SHA512/PATCHES/BASE_OPTIONS/OPTIONS_DEBUG
  └─ generate_vcpkg_json: features (含 description) + default-features
输出: ports/ffmpeg-8-1-1-shared/ + ports/ffmpeg-8-1-1-static/
```

## 使用
```bash
# 列出可用版本
python scripts/generate.py --list-families

# 生成特定版本
python scripts/generate.py --version 8.1.1

# 强制覆盖
python scripts/generate.py --version 8.1.1 --force
```

## 添加新版本
1. 创建族 YAML `X.Y.yaml` (继承 base 或同大版本上一个族)
2. 设置 include/exclude/defaults
3. 创建版本 YAML `X.Y.Z.yaml` (extends 族, sha512, patches)
4. 运行 `generate.py --version X.Y.Z --force`

## 添加新 feature
1. 在 `base.yaml` 的 `features` 中追加条目 (flag + description)
2. 在对应族 YAML 的 `include` 中添加 feature 名
3. 在 `define` 别名中引用 (可选)

## 与 ffmpeg-port-base.cmake 的关系
YAML 生成 portfile.cmake，设置变量供 base cmake 读取:
- `FFMPEG_VERSION` → `vcpkg_from_github` REF
- `FFMPEG_SHA512` → `vcpkg_from_github` SHA512
- `FFMPEG_SHARED_DIR` → 补丁 / 模板文件路径
- `FFMPEG_PATCHES` → 补丁列表
- `FFMPEG_BASE_OPTIONS` → 基础 configure 选项
- `FFMPEG_OPTIONS_DEBUG` → debug 模式 configure 选项

base cmake 通过 `if("feature" IN_LIST FEATURES)` 映射 feature → --enable-* flag。

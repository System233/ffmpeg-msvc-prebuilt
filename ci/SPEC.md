# CI/CD Architecture Specification

## Overview

本仓库为 FFmpeg 的 vcpkg 预构建项目。CI 系统负责：
- 检测上游 FFmpeg 新版本，自动创建 PR
- 检测 YAML 配置的 `revision` 变更，触发构建
- 每周构建 FFmpeg master 分支
- 构建产物发布为 GitHub Release，元数据写入 `data` 分支
- Vitepress SSG 从 `data` 分支读取元数据，生成静态站点

---

## 1. 分支架构

```
main                    data                     web                gh-pages
─────                   ────                     ───                ────────
ffmpeg/*.yaml           data/                    vitepress/         (GitHub Pages
  base.yaml              8.x/                   SSG 源码            自动部署)
  8.0.yaml                 build-index.yaml
  8.1.yaml                 ffmpeg-8.1.1-r2.yaml
  8.1.1.yaml               ffmpeg-8.1.1-r1.yaml
  ...                   7.x/
ports/                     build-index.yaml
  ffmpeg-8-1-1/            ...
  ...
patches/                 master/
scripts/                   build-index.yaml
vcpkg-config.json          ffmpeg-n8.2-dev-1-gabc1234.yaml
.github/workflows/
```

| 分支 | 内容 | 写权限 |
|------|------|--------|
| `main` | YAML 规格、ports、patches、scripts、workflows | 人工 + CI PR |
| `data` | 构建元数据 (version YAML + build-index) | CI finalize job |
| `web` | Vitepress SSG 源码 | 人工 |
| `gh-pages` | 部署产物 | GitHub Actions 自动 |

---

## 2. YAML 规格设计

### 2.1 `revision` 字段

- 定义在 patch YAML（如 `8.1.1.yaml`）中，不继承
- `revision` 未设置时默认 `0`
- 人工 bump `revision` 触发全量重建
- 修复部分失败变体时不 bump `revision`（已成功变体自动跳过）

```yaml
# ffmpeg/8.1.1.yaml
extends: "8.1"
revision: 2
source:
  sha512: e858e92e...
patches:
  - 0002-fix-msvc-link-8.1.patch
```

### 2.2 Variant YAML（build job 产出）

每个成功的 build variant 生成一个 `.var.yaml`，作为 artifact 上传。

```yaml
variant_id: "ffmpeg-8.1.1-r2-x64-windows-shared-gpl"
version: "8.1.1"
revision: 2
arch: x64
triplet: "x64-windows-mixed"
linkage: shared
license: gpl
lts: true
ffmpeg_tag: "n8.1.1"                  # null for master
ffmpeg_commit: null                    # git describe output for master
build_date: "2026-06-14T10:30:00Z"
asset_name: "ffmpeg-8.1.1-x64-windows-mixed-shared-gpl.zip"
file_size: 52428800
digest: "sha256:abc123def..."
features: [avcodec, avformat, x264, ...]
dependencies: [x264, x265, ffnvcodec-12, ...]
```

### 2.3 Version YAML（data 分支存储）

`import_yaml.py` 将多个 variant YAML 合并为单个 version YAML。

**路径：** `data/{major}.x/ffmpeg-{version}-r{revision}.yaml`

```yaml
# data/8.x/ffmpeg-8.1.1-r2.yaml
version: "8.1.1"
revision: 2
lts: true
ffmpeg_tag: "n8.1.1"                  # null for master
ffmpeg_commit: null                    # git describe output for master
release_tag: "ffmpeg-8.1.1-r2"         # "ffmpeg-{describe}" for master
release_id: 12345678
created: "2026-06-14T10:30:00Z"
updated: "2026-06-15T14:00:00Z"
variant_count: 22
total_variants: 24
complete: false
variants:
  - arch: x64
    triplet: "x64-windows-mixed"
    linkage: shared
    license: gpl
    asset_name: "ffmpeg-8.1.1-x64-windows-mixed-shared-gpl.zip"
    download_url: "https://github.com/.../download/..."
    file_size: 52428800
    digest: "sha256:abc123def..."
    features: [avcodec, avformat, x264, ...]
    dependencies: [x264, x265, ffnvcodec-12, ...]
  - arch: x64
    linkage: shared
    license: lgpl
    # ...
```

### 2.4 `build-index.yaml`（data 分支）

`variant_id` 到构建源的快速查找表。O(1) 判定某个 variant 是否已构建。

**路径：** `data/{major}.x/build-index.yaml`

```yaml
last_updated: "2026-06-15T14:00:00Z"
variants:
  - ffmpeg-8.1.1-r2-x64-windows-shared-gpl
  - ffmpeg-8.1.1-r2-x64-windows-shared-lgpl
  - ffmpeg-8.1.1-r2-arm64-windows-shared-gpl
  - ffmpeg-n8.2-dev-1-gabc1234-x64-windows-shared-gpl
```

master 分支的 build-index 路径：`data/master/build-index.yaml`

---

## 3. 变体 ID 与命名约定

### 3.1 Variant ID

| 类型 | 格式 | 示例 |
|------|------|------|
| 正式版 | `ffmpeg-{ver}-r{rev}-{triplet}-{link}-{license}` | `ffmpeg-8.1.1-r2-x64-windows-shared-gpl` |
| Master | `ffmpeg-{describe}-{triplet}-{link}-{license}` | `ffmpeg-n8.2-dev-1-gabc1234-x64-windows-shared-gpl` |

Master 的 `{describe}` 来自 `git describe --tags --abbrev=7`（在 FFmpeg 仓库中执行）。

### 3.2 Release Tag

| 类型 | 格式 | 示例 |
|------|------|------|
| 正式版 | `ffmpeg-{version}-r{revision}` | `ffmpeg-8.1.1-r2` |
| Master | `ffmpeg-{describe}` | `ffmpeg-n8.2-dev-1-gabc1234` |

### 3.3 Asset 文件名

| 类型 | 格式 | 示例 |
|------|------|------|
| 正式版 | `ffmpeg-{version}-{triplet}-{linkage}-{license}.zip` | `ffmpeg-8.1.1-x64-windows-mixed-shared-gpl.zip` |
| Master | `ffmpeg-{describe}-{triplet}-{linkage}-{license}.zip` | `ffmpeg-n8.2-dev-1-gabc1234-x64-windows-mixed-shared-gpl.zip` |

### 3.4 PR 分支

| 格式 | 示例 |
|------|------|
| `ci/ffmpeg-{version}` | `ci/ffmpeg-6.5` |

---

## 4. 构建矩阵

| 维度 | 值 |
|------|-----|
| Triplet | `arm-windows`, `arm64-windows`, `x86-windows`, `x64-windows` |
| License | `lgpl`, `gpl`, `nonfree` |
| Linkage | `shared`, `static` |

总计：4 × 3 × 2 = 24 variants / version

---

## 5. 保留策略

### 5.1 非 master 版本

- 每个 minor 版本组（如 `8.1.x`）仅保留最新 revision
- 每个 major（如 `8.x`）：最多保留 3 个 version 文件
- 超限删除：旧 version YAML → build-index 对应条目 → GitHub Release + tag

### 5.2 Master 版本

| 时间段 | 策略 |
|--------|------|
| < 7 天 | 全部保留 |
| 7~30 天 | 每自然周保留最新 1 个 |
| 30 天 ~ 1 年 | 每自然月保留最新 1 个 |
| > 1 年 | 每自然季度保留最新 1 个 |

### 5.3 执行

`retention-cleanup.yml` 每周日自动运行。

---

## 6. 安全模型

### 6.1 沙箱构建

- `build` 和 `seed` job：`permissions: {}`（零写入权限）
- 仅 `finalize` job 拥有 `contents: write`

### 6.2 vcpkg 基线锁定

仓库根目录 `vcpkg-configuration.json`：

```json
{
  "default-registry": {
    "kind": "git",
    "repository": "https://github.com/microsoft/vcpkg",
    "baseline": "<40-character-git-commit-hash>"
  }
}
```

CI 中额外锁定 vcpkg 工具自身版本：

```yaml
- run: git clone https://github.com/microsoft/vcpkg.git ${{ runner.temp }}/vcpkg
- run: git -C ${{ runner.temp }}/vcpkg checkout $BASELINE_COMMIT
```

---

## 7. Workflow 规范

### 7.1 `build-release.yml`（核心构建引擎）

**触发：** `workflow_dispatch` + `workflow_call`

**输入：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `version` | string | ✅ | 版本号（`8.1.1` 或 `master`） |
| `revision` | number | 正式版必需 | YAML 中定义的 revision 值 |
| `ffmpeg_ref` | string | master 必需 | `git describe --tags --abbrev=7` 输出 |
| `target_arch` | string | ❌ | 限制构建架构 |
| `target_license` | string | ❌ | 限制许可证类型 |

**作业：**

```
┌─ Job: seed (sandbox, permissions: {}) ──────────────────────────┐
│ • checkout main @ trigger commit                                │
│ • checkout vcpkg @ pinned commit                                │
│ • vcpkg install ffmpeg-deps → upload binary cache artifact      │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─ Job: build (sandbox, permissions: {}, fail-fast: false) ──────┐
│ • matrix: triplet × license × linkage                           │
│ • download seed cache                                           │
│ • Step 1: 读取 build-index → 跳过已构建 variant                 │
│ • generate.py → 生成 port                                       │
│ • vcpkg install ffmpeg-{ver}                                    │
│ • package_release.py → .zip + .var.yaml                         │
│ • upload artifacts:                                             │
│     ffmpeg-{ver}-{triplet}-{link}-{license}.zip                 │
│     ffmpeg-{ver}-{triplet}-{link}-{license}.var.yaml            │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─ Job: finalize (permissions: contents: write) ─────────────────┐
│ • 等待所有 build job 完成                                       │
│ • download 所有 .var.yaml + .zip artifacts                      │
│ • import_yaml.py:                                               │
│     ├─ 按 version+revision 分组 variant YAML                    │
│     ├─ 合并到 data/{major}.x/ffmpeg-{ver}-r{rev}.yaml           │
│     │   (新建或追加 variants 数组)                               │
│     ├─ 更新 data/{major}.x/build-index.yaml                     │
│     └─ git push data 分支                                       │
│ • 创建/追加 GitHub Release (gh release upload 幂等)             │
│ • git push release tag                                          │
└─────────────────────────────────────────────────────────────────┘
```

**跳过逻辑：**
```
variant_id = "ffmpeg-{ver}-r{rev}-{triplet}-{link}-{license}"
if variant_id in data/{major}.x/build-index.yaml.variants:
    skip
```

### 7.2 `scan-updates.yml`（上游扫描 + PR 创建）

**触发：** `schedule: 0 6 * * *` + `workflow_dispatch`

**作业：**

```
┌─ Job: scan ─────────────────────────────────────────────────┐
│                                                               │
│ 1. scan_updates.py → 获取上游 FFmpeg tags                     │
│                                                               │
│ 2. for each 新 tag (如 n6.5):                                 │
│    a. 检查 ffmpeg/{version}.yaml 是否存在                     │
│       存在 → 跳过（已有 YAML，不创建重复 PR）                  │
│       不存在 → 继续                                           │
│                                                               │
│    b. find_closest_yaml.py → 找最近版本 YAML                  │
│       算法: 同 major 内找最高 minor.patch                      │
│            无同 major → 全局最新版本                           │
│                                                               │
│    c. 复制 YAML → ffmpeg/{version}.yaml                       │
│       revision: 0                                             │
│                                                               │
│    d. generate.py → 生成 ports/ffmpeg-{X}-{Y}/                │
│                                                               │
│    e. git checkout -b ci/ffmpeg-{version}                     │
│       git add ffmpeg/ + ports/                                │
│       git push origin ci/ffmpeg-{version}                     │
│                                                               │
│    f. 检查分支是否已存在 → 是则跳过                            │
│                                                               │
│    g. gh pr create --title "ffmpeg {version}"                 │
│       --body "Auto-generated port for FFmpeg {version}"       │
└───────────────────────────────────────────────────────────────┘
```

### 7.3 `rev-update.yml`（YAML revision 检测）

**触发：** `push` to `main` with paths `ffmpeg/*.yaml`

**作业：**

```
┌─ Job: detect ───────────────────────────────────────────┐
│                                                           │
│ 1. ci_detect_changes.py:                                 │
│    对比 before/after git diff (仅 ffmpeg/*.yaml)         │
│    检测哪些 YAML 的 revision 字段变化                     │
│                                                           │
│ 2. 合并后 (pull_request closed + merged):                │
│    dispatch build-release:                                │
│      for each changed version:                           │
│        gh workflow run build-release.yml                 │
│          -f version={ver} -f revision={new_rev}          │
└──────────────────────────────────────────────────────────┘
```

### 7.4 `master-build.yml`（每周 master 构建）

**触发：** `schedule: 0 20 * * 5` (Friday 20:00 UTC+8)

**作业：**

```
┌─ Job: build-master ────────────────────────────────────────┐
│                                                              │
│ 1. clone ffmpeg/ffmpeg, checkout master                      │
│    describe = git describe --tags --abbrev=7                 │
│    (e.g. "n8.2-dev-1-gabc1234")                             │
│                                                              │
│ 2. find_closest_yaml.py → 找最接近的现有版本 YAML            │
│                                                              │
│ 3. 生成临时 port 配置（不写 YAML 文件到 main）                │
│                                                              │
│ 4. dispatch build-release:                                   │
│    gh workflow run build-release.yml                         │
│      -f version=master                                       │
│      -f ffmpeg_ref={describe}                                │
│                                                              │
│    构建成功 → Release tag: ffmpeg-{describe}                 │
│    data/master/ffmpeg-{describe}.yaml                        │
│    不提交 YAML 到 main                                       │
└──────────────────────────────────────────────────────────────┘
```

### 7.5 `retention-cleanup.yml`（保留策略执行）

**触发：** `schedule: 0 0 * * 0` (Sunday) + `workflow_dispatch`

**作业：**

```
┌─ Job: cleanup (permissions: contents: write) ────────────┐
│                                                            │
│ 1. checkout data 分支                                      │
│                                                            │
│ 2. retention_policy.py:                                    │
│                                                             │
│    非 master (data/{major}.x/):                            │
│      for each minor version 组:                             │
│        keep 最新 revision only                              │
│      for each major:                                       │
│        keep max 3 version files total                       │
│        → 删除旧 version YAML                                │
│        → 从 build-index 移除对应的 variant_id               │
│        → gh release delete + git push --delete tag          │
│                                                             │
│    master (data/master/):                                  │
│      < 7 天: 全部保留                                      │
│      7~30 天: 每自然周保留最新 1 个                          │
│      30 天~1 年: 每自然月保留最新 1 个                       │
│      > 1 年: 每自然季度保留最新 1 个                         │
│                                                             │
│ 3. git push data 分支                                       │
└─────────────────────────────────────────────────────────────┘
```

### 7.6 `pages.yml`（Vitepress 部署）

**触发：** `push` to `data` or `web` branch

**作业：**

```
┌─ Job: deploy ──────────────────────────────────────────┐
│                                                          │
│ 1. checkout web 分支                                     │
│ 2. checkout data 分支 → web/data/                         │
│ 3. npm ci && npm run build (vitepress build)             │
│ 4. deploy to GitHub Pages                                │
└──────────────────────────────────────────────────────────┘
```

---

## 8. 脚本规范

### 8.1 `scripts/generate.py`（修改）

**新增：**
- `get_revision(docs)` — 从 YAML 链读取 `revision`，倒数第一个定义者胜，默认 `0`
- `--all` 模式 — 对所有 leaf YAML（非 base）执行 `generate()`
- `generate_vcpkg_json()` — 输出 `"port-version": revision`（原硬编码 `0`）
- `generate_portfile()` — 输出 `set(FFMPEG_PORT_REVISION {revision})`

### 8.2 `scripts/find_closest_yaml.py`（新建）

**参数：** `--version {version_string}`

**返回：** 最近现有 YAML stem + 解析后的配置 dict

**算法：**
```
def find_closest_yaml(version: str) -> str:
    parts = version.split('.')
    major = parts[0]
    yaml_files = glob("ffmpeg/{major}.*.yaml") + glob("ffmpeg/{major}.*.*.yaml")
    if yaml_files:
        sort by (minor, patch) descending
        return latest
    else:
        # 无同 major YAML，返回全局最新
        return sorted(all_yamls)[-1]
```

### 8.3 `scripts/import_yaml.py`（新建）

**功能：**
1. 读取所有 variant `.var.yaml` 文件
2. 按 `version + revision` 分组
3. 每组合并到 `data/{major}.x/ffmpeg-{ver}-r{rev}.yaml`
   - 文件已存在 → 追加 `variants` 数组，更新 `updated` 时间
   - 文件不存在 → 创建（初始化 metadata + variants）
4. 更新 `data/{major}.x/build-index.yaml`，追加所有 variant_id 到 `variants` 数组
5. 自动创建不存在的目录

### 8.4 `scripts/retention_policy.py`（新建）

**功能：**
1. 遍历 `data/{major}.x/*.yaml`（非 build-index）
2. 按策略标记应删除的版本文件
3. 删除 version YAML 文件
4. 从 `build-index.yaml` 的 `variants` 数组中移除对应的 variant_id
5. 删除 GitHub Release（`gh release delete`）
6. 删除 git tag（`git push --delete origin {tag}`）

### 8.5 `scripts/get_features_for_version.py`（新建）

**功能：** 从 YAML 链提取指定版本 variant 的 `features` 和 `dependencies` 列表。

重用了 `generate.py` 的 `resolve_chain()`、`merge_features()`、`collect_deps()`。

### 8.6 `scripts/ci_detect_changes.py`（修改）

**变更：**
- 监视路径：从 `ports/ffmpeg-*` → `ffmpeg/*.yaml`
- 检测字段：`revision` 行变更
- 输出：`VERSION REVISION`（如 `8.1.1 2`）

### 8.7 `scripts/scan_updates.py`（修改）

**变更：**
- 结构化 JSON 输出新版本列表
- 排除已有 YAML 的版本

### 8.8 `scripts/package_release.py`（修改）

**变更：**
- 输出 `digest: sha256:...` 格式
- 生成 variant `.var.yaml` artifact
- 新增 `--revision` 参数

---

## 9. 部分失败修复流程

```
初始: 8.1.1 revision=1, 构建 24 variants
      → 20 成功, 4 失败
      → build-index: 20 entries
      → ffmpeg-8.1.1-r1.yaml: 20 variants, complete: false
      → Release: ffmpeg-8.1.1-r1 (20 assets)

修复: git push main（修改 YAML/patches，revision 保持 1）

rev-update:
  → 检测到 YAML 内容变化
  → revision 未变
  → dispatch build-release(version="8.1.1", revision=1)

build-release Step 1:
  → build-index 有 20 个 variant_id → skip
  → 4 个 variant_id 不存在 → 构建矩阵(4)

finalize:
  → 读 data/8.x/ffmpeg-8.1.1-r1.yaml
  → 追加 4 个 variant 到 variants 数组
  → complete: true
  → 追加 4 assets 到已有 Release
  → build-index 追加 4 个 variant_id
```

---

## 10. 数据流总览

```
┌───────────────────────────────────────────────────────────────────────┐
│                          DEVELOPMENT FLOW                             │
│                                                                       │
│  新上游 tag (n6.5)                                                    │
│       │ scan-updates.yml                                              │
│       ▼                                                               │
│  创建 ci/ffmpeg-6.5 PR                                                │
│       │ 人工审查                                                      │
│       ▼                                                               │
│  合并 → rev-update.yml 检测 → dispatch build-release                  │
│                                                                       │
│  YAML revision 变更 (人工)                                            │
│       │ push to main                                                  │
│       ▼                                                               │
│  rev-update.yml 检测 → dispatch build-release                         │
└───────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                          BUILD FLOW                                    │
│                                                                       │
│  build-release 接收 (version, revision [, ffmpeg_ref])                 │
│       │                                                               │
│       ├─ 读 data/{major}.x/build-index.yaml → 排除已构建变体           │
│       │                                                               │
│       ├─ seed (sandbox) → vcpkg install ffmpeg-deps → cache           │
│       │                                                               │
│       ├─ build matrix (sandbox, fail-fast: false)                     │
│       │   每成功变体 → .zip + .var.yaml → upload artifacts             │
│       │                                                               │
│       └─ finalize (write perms)                                       │
│            ├─ import_yaml.py: merge variants → version YAML            │
│            ├─ 更新 build-index.yaml                                    │
│            ├─ git push data                                            │
│            ├─ 创建/追加 GitHub Release                                 │
│            └─ git push release tag                                     │
└───────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                          MAINTENANCE FLOW                              │
│                                                                       │
│  retention-cleanup (weekly Sunday)                                     │
│       │                                                               │
│       ├─ 遍历 version YAML，按策略标记删除                              │
│       ├─ 删除 version YAML + build-index 对应条目                      │
│       ├─ 删除 GitHub Release + git tag                                 │
│       └─ git push data                                                 │
│                                                                       │
│  pages (push data/web)                                                 │
│       │                                                               │
│       ├─ vitepress build (从 data 分支读取元数据)                       │
│       └─ deploy to GitHub Pages                                        │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 11. 实施清单

| Phase | 内容 | 新建 | 修改 |
|-------|------|------|------|
| **1** | `revision` 字段 + `generate.py` | — | `generate.py`, YAML files, `SPEC.md` |
| **2** | vcpkg baseline 锁定 | `vcpkg-configuration.json` | CI workflows |
| **3** | `build-release.yml` 重写 | — | `build-release.yml`, `package_release.py` |
| **4** | data 分支脚本 | `import_yaml.py`, `retention_policy.py`, `get_features_for_version.py` | — |
| **5** | 工作流 | `rev-update.yml`, `master-build.yml`, `retention-cleanup.yml` | `scan-updates.yml`, `ci_detect_changes.py`, `scan_updates.py` |
| **6** | 辅助 + 前端 | `find_closest_yaml.py`, `web/` 全部源文件 | `pages.yml` |

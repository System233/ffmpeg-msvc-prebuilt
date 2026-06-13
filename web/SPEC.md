# FFmpeg MSVC Prebuilt — Web Portal 规格说明书

## 概述

单页应用（SPA），用于浏览、搜索和下载预编译的 FFmpeg Windows 二进制包。数据源由 CI 自动维护的 `catalog.json` 提供，部署于 GitHub Pages。

## 数据源

SPA 在运行时从仓库 main 分支获取清单文件：

```
GET https://raw.githubusercontent.com/BtbN/ffmpeg-msvc-prebuilt/main/catalog.json
```

### catalog.json 结构

`catalog.json` 由 `scripts/generate_port.py` 生成，格式如下：

```json
{
  "versions": [
    {
      "version": "8.1.1",
      "date": "2026-05-15",
      "builds": [
        {
          "arch": "x64",
          "license": "lgpl",
          "linkage": "shared",
          "size_bytes": 52428800,
          "filename": "ffmpeg-8.1.1-x64-lgpl-shared.zip",
          "release_id": 12345678
        }
      ]
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | FFmpeg 语义版本号 |
| `date` | string | ISO 8601 日期 (YYYY-MM-DD) |
| `builds` | array | 该版本下的构建产物列表 |
| `arch` | string | 目标架构: `x64` / `x86` / `arm64` / `arm` |
| `license` | string | 许可证类型: `lgpl` / `gpl` / `nonfree` |
| `linkage` | string | 链接方式: `shared` / `static` |
| `size_bytes` | number | 文件大小（字节） |
| `filename` | string | 压缩包文件名 |
| `release_id` | number | GitHub Release 资源 ID，用于构造下载 URL |
| `digest` | string | GitHub asset digest (e.g. "sha256:abc123...") |

下载 URL 格式：
```
https://github.com/BtbN/ffmpeg-msvc-prebuilt/releases/download/<release_id>/<filename>
```

## 页面

### 1. 首页 `/`

- 版本列表，按发布日期降序排列
- 每个版本卡片显示：版本号、发布日期、可用构建数量
- 搜索框：实时过滤版本号（防抖 300ms）
- 空状态："无匹配版本" 提示
- 响应式布局：移动端单列，桌面端（≥768px）双列

### 2. 版本详情（可选内联展开）

- 点击版本卡片展开/收起详情区域
- 详情区域展示构建矩阵（BuildMatrix）
- 矩阵行：架构（x64 / x86 / arm64 / arm）
- 矩阵列：许可证（lgpl / gpl / nonfree）→ 内分链接方式（shared / static）
- 每个单元格：文件大小（自动格式化 KB/MB/GB）+ 下载按钮
- 下载按钮链接至 GitHub Release assets
- 支持深链接：`/version/8.1.1` 直接打开并展开指定版本

## 组件

| 组件 | 职责 |
|------|------|
| `SearchBar` | 输入框，实时过滤版本列表 |
| `VersionList` | 版本卡片容器，处理加载/空/错误状态 |
| `VersionCard` | 单版本信息展示，含展开/收起按钮 |
| `BuildMatrix` | 架构×许可证×链接方式的三维表格 |
| `DownloadButton` | 显示文件大小 + 下载按钮，触发浏览器下载 |
| `ErrorBanner` | 错误状态提示 + 重试按钮 |
| `SkeletonCard` | 加载状态骨架屏 |

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | React 18+ |
| 构建工具 | Vite 5+ |
| 路由 | @tanstack/react-router v1 |
| 数据请求 | @tanstack/react-query v5 |
| UI 组件库 | shadcn-ui（Card / Button / Input / Table / Skeleton） |
| 样式 | Tailwind CSS 3 |
| 语言 | TypeScript 5 |

## 组件状态

每个数据驱动组件需覆盖以下状态：

### Loading（加载中）

- 首页：显示 4~6 个 `Skeleton` 卡片占位
- 详情：`BuildMatrix` 显示 `Skeleton` 表格占位

### Empty（空数据）

- 搜索结果为空："未找到匹配版本"
- 版本无构建："此版本暂无可用构建"

### Error（错误）

- 网络错误 / 解析失败："无法加载版本目录"
- 提供「重试」按钮，调用 `refetch()`

### Edge Cases（边界情况）

- catalog.json 缺少 `builds` 数组 → 显示 "暂无构建"
- 文件大小为 0 → 显示 "文件不可用" 禁用下载
- 版本号格式异常 → 照常显示原始字符串
- 日期缺失 → 隐藏日期显示

## 非功能需求

| 指标 | 目标 |
|------|------|
| 首次内容加载 | catalog.json < 100KB，加载 < 2s |
| 搜索过滤响应 | 输入后 < 100ms 展示结果 |
| 深链接 | `/version/8.1.1` 直接导航并展开 |
| 可访问性 | 按钮/链接使用语义化标签 |
| 浏览器兼容 | 最新两个主要版本 Chrome / Firefox / Edge |
| 包体积 | 压缩后 JS < 200KB（不含 React 运行时） |

## 路由设计

```
/                   → Home （版本列表）
/version/:version   → Home （自动滚动到并展开指定版本）
```

使用 `@tanstack/react-router` 的文件路由或扁平路由配置。

## 数据流

```
catalog.json (raw.githubusercontent)
       ↓
  @tanstack/react-query (fetch + cache)
       ↓
  VersionList / VersionCard → SearchBar 过滤
       ↓
  BuildMatrix → DownloadButton
```

- 使用 `useQuery` 获取并缓存 `catalog.json`
- 搜索过滤在前端执行，不产生额外网络请求
- 下载直接使用 `<a>` 标签 + `download` 属性或 `window.open`

## 部署

- GitHub Actions 构建后部署至 `gh-pages` 分支
- `vite build` 输出至默认 `dist/` 目录
- SPA 路由 fallback：`404.html` 或 `SPA` 模式配置

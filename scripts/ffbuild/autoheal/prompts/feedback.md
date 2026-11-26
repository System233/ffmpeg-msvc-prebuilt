
## 第 {attempt} 次尝试反馈
以下问题需要解决：
{violations}

只允许修改 agent_context.json 的 target_yaml 对应的 ffmpeg YAML，并新增目标独占引用的 Patch。禁止修改任何已有 Patch、其他版本、工具链及许可证门控。若无合法修复方案，保持 HEAD 和 tracked 文件不变，在 fix_report.md 写入 Decision: no_safe_fix 及 Root cause。

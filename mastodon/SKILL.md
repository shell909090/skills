---
name: mastodon
description: 连接 Mastodon 实例，读取时间线、搜索帖子、查看通知，以及按用户要求发布或回复。
---

# mastodon

使用本技能的 `scripts/mastodon.py`。相对路径以本 SKILL.md 所在目录为基准，不依赖调用者当前目录；执行前取得技能绝对路径，或切换到技能目录。

## 身份与运行环境

凭证固定为 `~/.config/agent/auth/mastodon.json.gpg`，允许 auth 目录是软链接。不得直接展示或手工解密凭证；仅让脚本内部加载。缺失时按[配置与用法](references/usage.md)指导操作者初始化，不搜索其他目录。

需要 Python 3.9+、GnuPG 及运行用户可用的解密私钥。

## 使用

先查看帮助或执行只读验证：

```bash
python3 scripts/mastodon.py --help
python3 scripts/mastodon.py verify
```

发布与回复按用户授权执行。时间线分页使用外层 ID，转发原文 ID 不能代替游标。默认 Markdown；程序处理可用 --json。

具体命令、字段、分页和错误处理见[配置与用法](references/usage.md)，根据当前操作读取相关部分。请求失败时报告错误，不通过输出凭证排查；写请求失败不应盲目重复提交。

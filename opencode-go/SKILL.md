---
name: opencode-go
description: 查询 OpenCode Go 订阅额度使用率与重置时间，不用于模型推理或本地历史成本统计。
---

# opencode-go

使用本技能的 `scripts/opencode-go.py`。相对路径以本 SKILL.md 所在目录为基准，不依赖调用者当前目录；执行前取得技能绝对路径，或切换到技能目录。

## 身份与运行环境

凭证固定为 `~/.config/agent/auth/opencode-go.json.gpg`，允许 auth 目录是软链接。不得直接展示或手工解密凭证；仅让脚本内部加载。缺失时按[配置与用法](references/usage.md)指导操作者初始化，不搜索其他目录。

需要 Python 3.9+、GnuPG 及运行用户可用的解密私钥。

## 使用

先查看帮助或执行只读验证：

```bash
python3 scripts/opencode-go.py --help
python3 scripts/opencode-go.py --json
```

仅查询用量。端点可能变化；返回百分比属于对应窗口，不能简单相加。人类可读时间固定为 Asia/Shanghai；JSON 保留服务端时间。

具体命令、字段、分页和错误处理见[配置与用法](references/usage.md)，根据当前操作读取相关部分。请求失败时报告错误，不通过输出凭证排查；写请求失败不应盲目重复提交。

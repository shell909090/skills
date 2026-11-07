---
name: trello
description: 使用 Trello 查询工作区、看板、列表和卡片，并按用户要求管理卡片、评论、成员和标签。
---

# trello

使用本技能的 `scripts/trello.py`。相对路径以本 SKILL.md 所在目录为基准，不依赖调用者当前目录；执行前取得技能绝对路径，或切换到技能目录。

## 身份与运行环境

凭证固定为 `~/.config/agent/auth/trello.json.gpg`，允许 auth 目录是软链接。不得直接展示或手工解密凭证；仅让脚本内部加载。缺失时按[配置与用法](references/usage.md)指导操作者初始化，不搜索其他目录。

需要 Python 3.9+、GnuPG 及运行用户可用的解密私钥。Trello 使用 Unix 文件锁，适用于 Linux/Unix。

## 使用

先查看帮助或执行只读验证：

```bash
python3 scripts/trello.py --help
python3 scripts/trello.py workspace list
```

先查询确认资源 ID，再执行用户要求的写操作。delete 永久删除，不能用归档需求代替删除授权。OAuth 需要浏览器同意，刷新自动加密写回；同一凭证只由一个节点刷新，编辑时暂停自动更新。

具体命令、字段、分页和错误处理见[配置与用法](references/usage.md)，根据当前操作读取相关部分。请求失败时报告错误，不通过输出凭证排查；写请求失败不应盲目重复提交。

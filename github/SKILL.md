---
name: github
description: 通过 GPG 凭证包装器使用 GitHub CLI，查询仓库、Issue、Pull Request、Actions、Release 和 Dependabot 漏洞提醒，并执行用户授权的管理操作。
---

# GitHub

使用本技能的 `scripts/github.sh`。相对路径以本 SKILL.md 所在目录为基准；执行前取得技能绝对路径，不依赖仓库克隆位置或调用者工作目录。

## 身份与环境

需要 Bash、GnuPG、jq、GitHub CLI（gh），Git 操作另需 Git。凭证固定为 `~/.config/agent/auth/github.json.gpg`，支持目录或文件软链接。只让脚本内部解密，不直接读取、展示凭证或运行 `gh auth token`。

包装器将 JSON 中的 `GH_TOKEN` 交给 gh；不执行登录、不写回凭证、不自动刷新。初始化、权限与同步约定见 [配置与用法](references/usage.md)。

## 使用

```bash
scripts/github.sh --version
scripts/github.sh repo view OWNER/REPO
scripts/github.sh issue list --repo OWNER/REPO --limit 30
scripts/github.sh dependabot list --repo OWNER/REPO
scripts/github.sh dependabot view 2 --repo OWNER/REPO
```

将 OWNER/REPO 替换为用户指定或当前项目确认的仓库。先用只读查询确认目标，再执行用户授权的写操作；创建 Issue、评论、PR 或发布 Release 都属于外部写入。

顶层命令白名单：`repo issue pr run workflow release search status label discussion ruleset attestation api dependabot`。具体命令是否存在取决于所安装的 gh 版本。不要绕过白名单改用裸 gh 或扩展。

需要正文时显式使用 `--body` 或 `--body-file`；长正文使用临时文件，放在系统临时目录的独立任务目录中，结束后清理。参数正确引用，不把用户输入拼接为 shell 代码。

列表默认可能截断；按需求使用命令支持的 `--limit`、筛选参数和 `--json`，不要把单页结果当成完整清单。失败时报告错误，不输出凭证；写操作结果不确定时先查询是否已生效，不盲目重试。

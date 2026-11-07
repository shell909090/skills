# GitHub CLI

只通过 `scripts/github.sh` 使用 GitHub CLI。不要直接读取、解密或输出 credential 文件，也不要运行 `gh auth token`。

## Credential

包装器解密 `~/.config/agent/auth/github.json.gpg`，读取 JSON 字段 `GH_TOKEN`，并只在 `gh` 子进程环境中提供 token。该 token 应使用 GitHub fine-grained PAT，并限制为必要的 resource owner、仓库、权限和有效期。

包装器默认主机为 `github.com`，关闭交互提示，设置 pager 为 `cat`、editor/browser 为 `false`。这减少交互及外部程序调用，但不是子进程隔离：gh 启动的 Git 等进程仍可能继承 token。`GH_HOST` 也不是主机访问白名单；本技能只用于用户授权的 github.com 资源。需要正文的命令应显式使用 `--body` 或 `--body-file`。

## 允许的命令

```text
repo issue pr run workflow release search status
label discussion ruleset attestation
```

其他顶层命令默认拒绝，尤其包括 `auth`、`api`、`alias`、`extension`、`config`、`secret`、`variable`、`ssh-key`、`gpg-key` 和 `codespace`。

## 常用操作

仓库：

```bash
scripts/github.sh repo view OWNER/REPO
scripts/github.sh repo list OWNER --json name,url,visibility
scripts/github.sh repo clone OWNER/REPO
```

Issue：

```bash
scripts/github.sh issue list --repo OWNER/REPO --json number,title,state,url
scripts/github.sh issue view 123 --repo OWNER/REPO
scripts/github.sh issue create --repo OWNER/REPO --title "Title" --body "Body"
```

Pull Request：

```bash
scripts/github.sh pr list --repo OWNER/REPO --json number,title,state,url
scripts/github.sh pr view 42 --repo OWNER/REPO
scripts/github.sh pr create --repo OWNER/REPO --title "Title" --body "Body"
scripts/github.sh pr checks 42 --repo OWNER/REPO
```

Actions：

```bash
scripts/github.sh run list --repo OWNER/REPO
scripts/github.sh run view RUN_ID --repo OWNER/REPO
scripts/github.sh workflow list --repo OWNER/REPO
```

Release：

```bash
scripts/github.sh release list --repo OWNER/REPO
scripts/github.sh release view TAG --repo OWNER/REPO
```

## 权限

GitHub token 是主要权限边界。建议默认只授予 `Metadata: read`、`Contents: read`、`Issues: read`、`Pull requests: read` 和 `Actions: read`；确实需要对应写操作时再把单项权限改为 `write`。不要默认授予 `Administration`、`Secrets`、`Webhooks` 或 `Workflows`。

包装器的命令白名单是第二层限制，不能扩大 fine-grained PAT 的权限。

## 初始化与跨机同步

由操作者创建 fine-grained PAT，选择所需 resource owner、仓库、权限及有效期，再用支持 GPG 的编辑器保存以下 JSON 为 `~/.config/agent/auth/github.json.gpg`：

```json
{"GH_TOKEN": "YOUR_FINE_GRAINED_PAT"}
```

文件应使用操作者选定的 GPG 接收者加密；不要将真实 token 放进命令行参数、对话、日志或普通临时文件。不需要 `gpg_recipient` 字段，因为脚本只读，不负责加密写回。

同步密文到需要访问的机器，并由操作者分别配置可解密该密文的 GPG 私钥或硬件密钥。私钥不随此仓库分发。统一 auth 入口可链接到实际同步目录。脚本不会更换 PAT，因此无需 OAuth refresh 锁；到期或撤销后由操作者生成替代 PAT、更新密文并同步。手工编辑应避免多机同时覆盖。

gh 通过 `GH_TOKEN` 使用该凭证，不需要 `gh auth login`，也不需要同步系统 keyring。普通 gh 配置仍由 gh 自身管理，包装器不重定向配置目录。Git SSH 操作使用 SSH 身份，不由此 PAT 自动提供认证。

## 验证与故障

先运行 `scripts/github.sh --version`，不读取凭证。然后对已授权仓库运行 `scripts/github.sh repo view OWNER/REPO` 验证只读访问。

缺失凭证时按上面的固定路径初始化，不搜索其他位置。解密失败时由操作者检查 GPG 私钥及解锁状态；401/403/404 时检查 PAT 有效期、组织审批、仓库选择和权限，私有资源的 404 也可能表示无权访问。不要把 PAT 权限一律扩大来解决问题。

列表命令按各自 `--help` 使用 `--limit`；不同命令支持的选项不同，包装器不提供统一分页。顶层白名单仅限制入口，不保证其中所有子命令只读；PAT 权限是服务端访问边界。

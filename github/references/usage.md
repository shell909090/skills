# GitHub CLI

只通过 `scripts/github.sh` 使用 GitHub CLI。不要直接读取、解密或输出 credential 文件，也不要运行 `gh auth token`。

## Credential

包装器解密 `~/.config/agent/auth/github.json.gpg`，读取 JSON 字段 `GH_TOKEN`，并只在 `gh` 子进程环境中提供 token。该 token 应使用 GitHub fine-grained PAT，并限制为必要的 resource owner、仓库、权限和有效期。

包装器默认主机为 `github.com`，关闭交互提示，设置 pager 为 `cat`、editor/browser 为 `false`。这减少交互及外部程序调用，但不是子进程隔离：gh 启动的 Git 等进程仍可能继承 token。`GH_HOST` 也不是主机访问白名单；本技能只用于用户授权的 github.com 资源。需要正文的命令应显式使用 `--body` 或 `--body-file`。

## 允许的命令

```text
repo issue pr run workflow release search status
label discussion ruleset attestation api dependabot
```

其他顶层命令默认拒绝，尤其包括 `auth`、`alias`、`extension`、`config`、`secret`、`variable`、`ssh-key`、`gpg-key` 和 `codespace`。

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

## Dependabot 漏洞提醒

`dependabot` 子命令将参数转换为 `gh api` 的 GET/PATCH 请求，使用同一套凭证。

```bash
scripts/github.sh dependabot list --repo OWNER/REPO
scripts/github.sh dependabot list --repo OWNER/REPO --state all
scripts/github.sh dependabot view 2 --repo OWNER/REPO
scripts/github.sh dependabot update 2 --repo OWNER/REPO --state dismissed --dismissed-reason tolerable_risk --dismissed-comment 'Accepted risk'
scripts/github.sh dependabot update 2 --repo OWNER/REPO --state open
```

列表默认查询 open，`--state all` 查询全部状态；内部使用 `gh api --paginate` 获取所有分页，输出各页 JSON 数组。需要合并时可配合 `jq -s 'add // []'`，并启用 `set -o pipefail` 保留 API 失败退出码。单条查询输出 JSON 对象。修改使用 PATCH，字段取值和读写权限由 GitHub 服务端判定。也可通过包装器的 `api` 命令直接使用 gh 原生参数。

Fine-grained PAT 需要目标仓库的 **Dependabot alerts** 权限，查询需要 read，修改需要 write；由服务端决定操作是否获准。仓库可读不代表提醒可读；若返回 403 `Resource not accessible by personal access token`，检查该项权限。

## 权限

GitHub 服务端根据 token 的仓库范围和权限判定操作是否获准。脚本支持查询和写操作，不要求 token 固定为只读。按实际使用的功能配置 fine-grained PAT；下表是常见对应关系，不是所有命令的完整权限清单。

| 所需权限 | 许可操作 | 支持的子命令 | 注释 |
| --- | --- | --- | --- |
| `Metadata: read` | 读取仓库基本信息 | `repo view/list`、`api` | fine-grained PAT 的基础仓库权限 |
| `Contents: read` | 读取文件、提交和 Release | `repo`、`release list/view/download`、`api` | 此处指相关查询；Git SSH 操作使用 SSH 身份 |
| `Issues: read` | 读取 Issue 及相关信息 | `issue list/view`、`label list`、`search issues`、`api` | 标签接口也可能接受 `Pull requests: read` |
| `Pull requests: read` | 读取 PR、差异及相关信息 | `pr list/view/diff`、`search prs`、`api` | PR 检查结果可能涉及 Actions 或提交状态接口 |
| `Actions: read` | 读取 workflow、运行记录、日志和产物 | `run list/view/download`、`workflow list/view`、`api` | 触发、取消等写操作不属于此权限 |
| `Dependabot alerts: read` | 读取漏洞提醒列表和详情 | `dependabot list/view`、`api` | 与仓库内容权限独立 |
| `Attestations: read` | 读取仓库的证明记录 | `attestation`、`api` | 具体命令可能访问额外的验证材料或服务 |

表中子命令仅指对应的查询操作，不表示其所有功能都由该权限覆盖。`ruleset`、`discussion`、`status` 及其他聚合查询依实际资源和接口判定；例如仓库规则查询与组织规则查询可能有不同权限要求。写操作需要按具体接口补充 write 等权限，不在此只读表中展开。

`api` 可以调用不同资源的接口，没有一组固定权限能代表所有用途。Discussion、标签、搜索、组织资源等操作也应按实际接口确认权限及 fine-grained PAT 支持情况。部分接口需要多项权限，部分支持公开资源的匿名读取。以 [GitHub 官方权限表](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens) 和具体接口文档为准；REST 响应的 `X-Accepted-GitHub-Permissions` 头也可帮助定位所需权限。

包装器白名单只限定命令入口，不代替服务端授权，也不会扩大 token 权限。

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

列表命令按各自 `--help` 使用 `--limit`；不同命令支持的选项不同，API 列表使用 `--paginate`，包装器不提供额外分页封装。顶层白名单仅限制入口，不保证其中所有子命令只读；PAT 权限是服务端访问边界。

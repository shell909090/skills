# mastodon 配置与用法

以下命令在技能目录执行；从其他位置调用时将脚本路径替换为本技能的绝对路径。

## 初始化

由操作者取得服务凭证，以以下 JSON 字段保存为 `~/.config/agent/auth/mastodon.json.gpg`。字段名不是环境变量注入入口；脚本仅使用该 GPG 文件。

```json
{"MASTODON_BASE_URL": "https://social.example", "ACCESS_TOKEN": "YOUR_ACCESS_TOKEN"}
```

在所用实例的开发设置中创建应用并取得 access token，按下表选择所需 scopes。

由操作者用自己的 GPG 公钥加密 JSON；可用 Emacs 编辑加密文件。不要把实际值交给助手或保存到仓库。GPG 根据密文选择私钥，无需硬编码公钥指纹。

## 命令

| 子命令 | Mastodon API | 权限 | 用途 |
|---|---|---|---|
| `verify` | `GET /api/v1/accounts/verify_credentials` | `profile` / `read:accounts` | 验证凭据并返回当前账号 |
| `home` | `GET /api/v1/timelines/home` | `read:statuses` | 读取主页时间线 |
| `public` | `GET /api/v1/timelines/public` | 通常公开 | 读取公共时间线 |
| `tag` | `GET /api/v1/timelines/tag/:hashtag` | 通常公开 | 读取标签时间线 |
| `trends` | `GET /api/v1/trends/:type` | 公开 | 读取热门标签、帖子或链接 |
| `search` | `GET /api/v2/search` | `read:search` | 搜索账号、标签或帖子 |
| `status` | `GET /api/v1/statuses/:id` | 公开或 `read:statuses` | 读取单条帖子 |
| `context` | `GET /api/v1/statuses/:id/context` | 公开或 `read:statuses` | 读取帖子的祖先和回复 |
| `notifications` | `GET /api/v1/notifications` | `read:notifications` | 读取通知 |
| `post` | `POST /api/v1/statuses` | `write:statuses` | 发布帖子或回复 |

### 账号和时间线

```bash
python3 scripts/mastodon.py verify
python3 scripts/mastodon.py home                          # 本次最多 400 条
python3 scripts/mastodon.py home --limit 120              # 一般 3 页；过滤或重复可能需要更多，最多 10 次请求
python3 scripts/mastodon.py home --limit 120 --next <cursor>
python3 scripts/mastodon.py public --local --limit 20
python3 scripts/mastodon.py tag python --limit 20
python3 scripts/mastodon.py notifications --limit 20
```

`home`、`public`、`tag` 和 `notifications` 的 `--limit` 表示本次合并去重后的总条数上限，默认 400，范围 1 到 400。脚本自动翻页，每个 API 请求最多取 40 条，每次调用最多发出 10 个 API 请求；即使短页或重复导致总量不足，也不会突破此上限。`--limit > 400` 理论上需要超过 10 页，会在参数解析时直接拒绝，不联网。`public` 还支持 `--local`。

这些端点支持 `--max-id`、其别名 `--next <cursor>`、`--since-id` 和 `--min-id`。默认向较旧方向翻页，输出 `Next: --next <外层id>` 供下一次调用继续；使用 `--min-id` 时向较新方向翻页，输出 `Next: --min-id <cursor>`。`--min-id` 不能与 `--max-id`（含 `--next`）同时使用。时间线以外层帖子 ID 合并去重及分页，通知使用通知自己的 ID；转发原文的 `reblog.id` 不能作为时间线游标。

自动翻页的停止条件：

- 空页停止；不能仅凭短页断定耗尽。
- 游标重复或没有新增条目时停止，并标记结果不完整。
- 达到本次总条数或 10 次请求上限时停止，并标记可能还有结果。
- 任一请求出错，整次调用失败并以非零状态码退出，不输出伪装完整的部分结果。

Markdown 展示合并结果及 `Item count`、`Pages fetched`、`Stopped` 和可用时的 `Next`；空结果无游标。`Next` 只是继续尝试的游标，不保证后续有数据。时间线还显示原创（排除回复）、回复、转发总数，以及按时间线外层账号统计的条数；通知不显示帖子统计。`context`、`search` 等非上述自动分页端点不显示该游标。

### 热门趋势

```bash
python3 scripts/mastodon.py trends                         # 默认热门标签
python3 scripts/mastodon.py trends --type statuses --limit 20
python3 scripts/mastodon.py trends --type links --limit 10 --offset 10
python3 scripts/mastodon.py trends --type tags --json
```

`--type` 可选 `tags`（默认）、`statuses`、`links`。标签和链接默认 10 条、最多 20 条；帖子默认 20 条、最多 40 条。`--offset` 为非负整数，默认 0。只请求一页，无自动分页或 ID 游标。结果按实例趋势分数排序，分数会变动，跨页可能重复或遗漏。默认 Markdown 显示帖子正文或标签/链接及每日统计；`--json` 保留完整原始结果。

参考：[官方 trends 文档](https://docs.joinmastodon.org/methods/trends/)。

### 搜索和帖子

```bash
python3 scripts/mastodon.py search "query" --type statuses --limit 20
python3 scripts/mastodon.py search "https://social.example/@EXAMPLE_USER/STATUS_ID" --type statuses --resolve --limit 1
python3 scripts/mastodon.py status <STATUS_ID>
python3 scripts/mastodon.py context <STATUS_ID>
```

`search --limit` 仍为 1 到 40，默认 20，没有自动分页。`search --type` 可选 `accounts`、`hashtags`、`statuses`。跨实例帖子 URL 使用 `--resolve`，再从搜索结果取得当前实例的本地状态 ID；所有 ID 都应按不透明字符串处理。

### 发布和回复

```bash
python3 scripts/mastodon.py post "message" --visibility public
python3 scripts/mastodon.py post "reply" --reply-to <STATUS_ID>
```

`--visibility` 可选 `public`、`unlisted`、`private`、`direct`，默认 `public`。

## 输出和限制

- 默认输出 Markdown，正文去除 HTML 后完整显示，不再截断为 400 个字符。通常阅读和分页无需 JSON。
- 每条帖子显示 `Timeline ID`（外层 `id`）、`Type`（`original` / `reblog`）、`Timeline account` 及 account ID、`Timeline created`，以及内容作者及 account ID、`Status ID`、`created_at`、`url`、`language`、`visibility`、`in_reply_to_id`、CW（如有）和完整正文。
- 转发明确显示 `Boosted by`：外层时间线条目记录转发账号、ID 和时间，内层 `reblog` 记录原作者与原帖；通知内含的帖子也使用上述完整格式。
- 按 `reblog` 是否存在区分转发和非转发；`Type: original` 的非转发也包含回复，筛选纯原创还需检查 `in_reply_to_id` 是否为空。按账号聚合时，需明确使用外层转发账号还是内层原作者。
- 精确的程序合并、聚合或读取完整原始数据仍使用 `--json`。参数可放在子命令前或后，例如 `python3 scripts/mastodon.py --json home` 或 `python3 scripts/mastodon.py home --json`。所有 ID 均按不透明字符串处理，不同实例的 ID 不能混用。
- 自动分页端点的 JSON 标准输出仍是一个合并去重后的数组，保留原始条目字段；摘要和 `Next` 写到标准错误，方便程序读取数组。跨次调用的合并、去重或进一步聚合由调用方处理。
- 错误写到标准错误，并以非零状态码退出。
- `Status.content` 是经过清理的 HTML。
- 搜索结果受实例策略、联邦同步和搜索后端影响。
- 常见错误为 `401` 凭据无效、`403` 权限不足、`404` 不存在或不可见、`422` 参数错误、`429` 限流。

## 官方文档

- API：https://docs.joinmastodon.org/api/guidelines/
- OAuth 权限：https://docs.joinmastodon.org/api/oauth-scopes/

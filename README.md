# Skills

一套供 Codex、Claude Code、OpenCode 和 Hermes 使用的共享技能仓库。目标是提供可执行的操作说明与工具，为 AI 助手建立可用的服务连接环境。

技能源文件在本仓库维护，客户端通过软链接或外部目录发现；身份信息独立保存在 GPG 文件中。架构与维护约定见 [AGENTS.md](AGENTS.md)。

## 技能

- [amap](amap/SKILL.md)：使用高德地图查询地址坐标、搜索地点，以及规划驾车、公交或步行路线。
- [falai](falai/SKILL.md)：通过 fal.ai 查找模型、提交和跟踪媒体推理任务、取得结果或查询账户 credits。
- [mastodon](mastodon/SKILL.md)：连接 Mastodon 实例，读取时间线、搜索帖子、查看通知，以及按用户要求发布或回复。
- [opencode-go](opencode-go/SKILL.md)：查询 OpenCode Go 订阅额度使用率与重置时间，不用于模型推理或本地历史成本统计。
- [trello](trello/SKILL.md)：使用 Trello 查询工作区、看板、列表和卡片，并按用户要求管理卡片、评论、成员和标签。

## 目录

```text
仓库/
  AGENTS.md
  README.md
  Makefile
  scripts/install.py
  <skill-name>/
    SKILL.md
    scripts/       # 可选
    references/    # 可选
```

## 安装

需要 Unix 类系统、Python 3 和 Make。在仓库目录运行：

```bash
make check            # 检查技能命名与安装目标冲突
make install          # 安装两个发现入口的逐技能软链接
make uninstall        # 仅移除仍指向本仓库技能的链接
make hermes-config    # 输出 Hermes 配置片段
```

重复安装不复制源文件，不覆盖其他技能。已有目标发生冲突时，安装前报错。卸载不删除源文件或无关目标；移除技能目录前应先卸载，避免留下失效链接。仓库搬迁后需清理旧链接并重新安装。

| 客户端 | 本仓库使用的发现入口 |
|---|---|
| Codex | `~/.agents/skills/<name>` |
| Claude Code | `~/.claude/skills/<name>` |
| OpenCode 2 | 读取以上两处，按 skill ID 合并 |
| Hermes | `skills.external_dirs` 直接指向仓库 |

“不遗漏”是安装所有有效技能到两个必需入口；“不重复”是只维护一份源文件，OpenCode 2 最终只保留一个相同 ID 的技能。**两个目录仍会被扫描、读取两次。** 此行为已核对 OpenCode v2.2.5 源码；旧版或未来版本需重新核实。请勿在其他发现路径、项目或插件中添加本仓库的同名副本。客户端禁用设置或外部同名技能仍可能影响可用性。

安装目标可用于隔离测试：

```bash
make install AGENTS_DIR=/your/test/agents CLAUDE_DIR=/your/test/claude
```

## Hermes

执行 `make hermes-config`，将输出合并到所用 profile 的配置文件中。默认是 `~/.hermes/config.yaml`，例如：

```yaml
skills:
  external_dirs:
    - /absolute/path/to/this/repository
```

保留现有配置，只加入一次仓库路径。不同时加入 `.agents/skills`、`.claude/skills` 或本地同名副本。Hermes 支持外部目录，但项目、本地和 create_dir 中的同名技能具有更高优先级。用 `hermes skills list` 核对结果；必要时重启会话。

外部目录不是写保护机制，Hermes 可原地修改可写文件。需要只读使用时应通过文件权限落实。安装器不会自动修改 YAML 或接管 Hermes 内置技能目录。

## 身份信息

所有技能统一读取 `~/.config/agent/auth/<service>.json.gpg`。由操作者创建目录，或把 `auth` 目录软链接到其管理的实际位置。凭证不随 skills 安装，不进入 Git。

直接采用 GPG 加密 JSON，便于用 Emacs 透明编辑。操作者完成注册、权限选择和授权；技能脚本内部使用凭证。各服务的字段和初始化方式由对应技能说明。自动刷新与手动编辑不能同时无协调地写同一文件。

## 参考与兼容性依据

- [Codex 技能发现路径及软链接支持](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code 技能目录](https://code.claude.com/docs/en/skills)
- [OpenCode 技能发现路径](https://docs.opencode.ai/docs/skills/)
- [OpenCode v2.2.5 读取及按 ID 合并实现](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/config/plugin/skill.ts)
- [Hermes 外部技能目录](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md#external-skill-directories)

核对日期：2026-11-07。客户端升级后，应重新验证发现和重复名称处理行为。

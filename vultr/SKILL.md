---
name: vultr
description: 查询 Vultr 账户流量、实例用量及账单，完成 OAuth 授权与令牌刷新；不用于创建或修改云资源。
---

# Vultr

运行本技能目录中的 `scripts/vultr.py`。需要 Unix、Python 3.9+、GnuPG 和可用的私钥；不需要 pip 包。

- `summary`（默认）：账户余额、流量和待扣费用。
- `instances`：逐实例流量。
- `charges`：未出账费用；`history -n 10`：账单历史。
- 查询可加 `--json`；实例 JSON 是汇总后的结构。
- `login`：操作者在 Console 授权，随后在交互终端隐藏粘贴完整回调 URL。
- `show`：只显示凭证存在状态、有效期和未完成刷新标记。
- `refresh`：检查并按需刷新，未临期不强制轮换；查询也自动刷新。

凭证入口固定为 `~/.config/agent/auth/vultr.json.gpg`。初始化、OAuth 权限、回调和存储部署见 [references/usage.md](references/usage.md)。缺失时不要搜索其他路径或打印解密内容。

**轮换凭证必须由单机管理，不同步到多机使用。** 若 auth 目录会同步，将此文件软链接到不同步的本机目录。锁只保护同一实际路径上的本机进程；旧脚本、人工编辑和同步程序不遵守本技能锁。迁移时停用旧刷新任务，人工编辑前暂停调用。

`refresh_pending` 表示上次刷新结果不确定：停止重试，由操作者重新 `login`，不要清除标记或恢复旧备份继续刷新。API 查询只发 GET；OAuth 交换会更新认证文件，不修改云资源。权限由用户所配 IAM policy 决定，脚本不保证 token 本身只读。

先用 `show` 检查部署，再以 `history -n 1` 验证只读访问。不要将真实账户输出保存进仓库。分页最多 40 页，超限报错；GET 遇 429 最多等待 30 秒重试一次，token 交换不自动重试。

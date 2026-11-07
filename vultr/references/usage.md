# Vultr 使用与认证

## 部署和依赖

Python 3.9+ 标准库、Unix `fcntl` 文件锁、GnuPG、系统 CA 证书和网络。时间按本机时区显示。脚本仅从 `~/.config/agent/auth/vultr.json.gpg` 读取，不提供路径参数或环境变量覆盖。

若 auth 目录由同步程序管理，将 `vultr.json.gpg` 单文件链接到**明确排除同步的本机目录**，例如 `~/.local/state/agent/auth/vultr.json.gpg`。实际目录权限 700、文件 600。每台机器必须独立授权；同一授权的 refresh token 不可复制共享。本技能不会自动移动或覆盖现有凭证。已有文件时先停止所有旧脚本和刷新任务，再移动密文、建立链接并检查同步规则；不要用复制方式留下两个可刷新副本。其他机器不能靠复制该密文完成迁移。

脚本解析整个凭证路径的软链接；与 Trello 一样，在本机系统临时目录的 `vultr-<UID>/<实际凭证路径的SHA256>` 建立锁，通常位于 `/tmp/`，不放入凭证目录或同步目录。系统临时目录须为本机不同步目录。此锁文件在释放锁时不删除，所有调用对同一 inode 使用 `flock`，等待最多 60 秒。取得锁后才读取、检查有效期、刷新并写回；退出或进程崩溃会释放内核锁。旧 `vultr-token.py` 不得继续运行。

凭证更新用实际目录内唯一临时密文、文件 fsync、原子替换及目录 fsync，保留入口软链接。请求前先加密保存 `refresh_pending` 标记；这也验证接收者与写盘能力。成功保存新 token 后删除标记。网络失败、进程中断或后续写盘失败时标记保留，下次拒绝重用旧 token，须重新授权。无法保证网络服务端与本地磁盘的跨系统事务，故采用保守停止策略。不要在调用期间手动编辑凭证；普通编辑器不遵守脚本的锁。

## 撞锁与补偿边界

同步软件不提供分布式锁。即便设定等待 interval，两台机器也可能在各自副本上同时获得本机锁，并在等待结束时仍看不到对方的变更。`refresh_pending` 同样会延迟同步，所以它只保证本机未被外部覆盖的凭证文件在故障后停止重试，不能检测或修复所有跨机冲突。

认证生命周期的补偿规则：

1. 本机锁竞争：阻塞等待，获得锁后重读最新凭证；超过 60 秒退出，不发请求。
2. 请求已开始但未确认新凭证落盘：保留 `refresh_pending`，后续停止刷新。宁可要求重新授权，也不猜测旧 refresh token 是否仍有效。
3. 发现同步冲突、旧副本覆盖、重复刷新或服务端拒绝令牌：停止所有共享该授权的刷新任务，隔离同步副本。由操作者重新授权并在唯一刷新端保存新 token；不要自动轮流尝试冲突文件中的 refresh token，也不要回滚旧备份。
4. 恢复：`login` 成功写回后清除未完成标记，再执行只读查询验证；其他机器改用独立授权，或通过统一刷新端访问。

第 1、2 项及 login 清除标记已经由脚本实现。第 3 项的跨机冲突发现与停机由部署侧负责，当前脚本没有分布式协调服务，不能声称自动补偿了多机撞锁。服务端已撤销 token family 时，单纯等待同步无法恢复，必须重新授权。

未来若必须共享同一授权，优先采用单一刷新服务，其他机器通过它请求访问；若采用分布式租约，还必须防止租约过期后的旧持有者继续请求。Vultr token 端点不接受我们自己的 fencing token，因此仅加一个分布式锁仍不足以保证安全。授权轮换是不可回滚的外部操作，补偿的终点是安全停止与重新授权，而不是重放旧 token。

## 初始化 OAuth

在 Vultr Console 创建 OAuth Application，关联 OIDC provider 和所需 IAM policy，登记 callback。Draft 应用可由 allowlist 中的账户测试；app owner 自动加入。记录 client id、secret 和 provider id（OAuth client 的 `oidc_provider_id`）。

流量及账单查询使用的权限：`account.billing.Read`、`account.bandwidth.Read`、`compute.instance.List`、`compute.instance.Read`、`metrics.instance.List`。权限取决于你的应用配置，不预设或扩大授权。

用支持 GPG 的编辑器创建加密 JSON（下列均为占位符）：

```json
{
  "provider_id": "YOUR_PROVIDER_ID",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "callback": "http://localhost:8765/callback",
  "gpg_recipient": "YOUR_GPG_PUBLIC_KEY_FINGERPRINT"
}
```

已有 token 的文件保留原字段，添加自己的 `gpg_recipient` 即可。解密无需配置私钥指纹；加密写回需要接收者公钥。不要把 secret 放在命令行、普通临时文件或对话里。

运行 `python3 scripts/vultr.py login`，按提示在 Console 选择该应用授权。浏览器跳转到注册的 callback 后复制完整 URL，粘贴到脚本的隐藏输入。脚本不监听端口，浏览器提示连接失败不影响地址栏中的 code；callback 必须与配置完全一致。不要接受他人提供的授权回调。该模式由操作者发起并选择 Console 授权，未自动构造带 state/PKCE 的浏览器授权 URL。

脚本使用应用 Basic 认证交换授权码，form 字段为 `redirect_url`；完成后写入 access/refresh token、expires_at 等字段。不提供旧的独立 listen/pending 明文文件流程。

官方流程和轮换语义见 [Vultr OAuth 集成说明](https://docs.vultr.com/platform/iam/oauth/access-tokens/how-to-integrate-a-third-party-app-with-vultr-oauth)。授权码一次性且有效 10 分钟；refresh token 每次轮换，30 天滑动过期，重用旧值可能撤销整组 token。长期停用后须重新授权。

`show` 只读取一次完整快照，不加锁、不等待刷新结束。原子替换保证读取到完整旧版或新版；状态可能随后变化，`refresh_pending` 也可能表示刷新正在进行，而非已失败。

## 查询

以下命令在技能目录下运行，也可使用脚本的绝对路径：

```bash
python3 scripts/vultr.py show
python3 scripts/vultr.py history -n 1
python3 scripts/vultr.py summary
python3 scripts/vultr.py instances --json
python3 scripts/vultr.py charges
python3 scripts/vultr.py refresh
```

账户、带宽、账单和实例端点均位于 `https://api.vultr.com/v2/`。不支持资源写操作或 Bare Metal 流量。HTTP 错误隐藏响应正文；不跟随重定向。

账户 `balance` 取反作为可用余额显示，同时保留原值。实例字节除以 1024³ 显示 GiB；账户带宽字段沿用原脚本的 GiB 展示约定，`--json` 保留 API 字段供核对。`allowed_bandwidth=0` 显示为未提供单独额度。`history` 按条数提前停止分页；达到分页上限时报错，不把截断结果当完整结果。

退出码：0 成功，2 配置或凭证问题，3 请求或数据问题，130 用户取消。

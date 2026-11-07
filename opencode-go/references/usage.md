# opencode-go 配置与用法

以下命令在技能目录执行；从其他位置调用时将脚本路径替换为本技能的绝对路径。

## 初始化

由操作者取得服务凭证，以以下 JSON 字段保存为 `~/.config/agent/auth/opencode-go.json.gpg`。字段名不是环境变量注入入口；脚本仅使用该 GPG 文件。

```json
{"OPENCODE_GO_API_KEY": "YOUR_OPENCODE_API_KEY"}
```

在 OpenCode 账户控制台取得可用于订阅用量查询的 API Key。

由操作者用自己的 GPG 公钥加密 JSON；可用 Emacs 编辑加密文件。不要把实际值交给助手或保存到仓库。GPG 根据密文选择私钥，无需硬编码公钥指纹。

## 使用

从本目录执行：

```bash
python3 scripts/opencode-go.py
python3 scripts/opencode-go.py --json
```

默认输出人类可读的用量与重置时间；`--json` 返回服务端 JSON。退出码：`0` 成功、`2` 凭证缺失、`3` 请求或解析失败。

## 输出含义

- `rolling`、`weekly`、`monthly` 分别表示滚动、周和月窗口。
- `percent` 是对应窗口的额度使用百分比，不是实际消费金额；各窗口的比例不能简单相加。
- `resetsAt` 为服务端返回的 UTC 重置时间。当前脚本的人类可读输出固定使用 `Asia/Shanghai`，其他时区的部署者可调整源码，或使用 JSON 中的 UTC 时间。
- `status` 非 `ok` 时，脚本会在对应行显示状态。

## 接口边界

脚本目前请求 `GET https://opencode.ai/zen/go/v1/usage`，认证头为 `Authorization: Bearer YOUR_OPENCODE_API_KEY`。

应将此端点视为可能变化的实现依赖，不把它当成已承诺稳定性的公开 API。部署时需验证当前账户是否能使用；认证失败应检查凭证，请求或解析失败应检查接口是否变化。脚本不读取 OpenCode 客户端的登录态文件。

服务端窗口统计与客户端本地历史成本统计的含义不同，不能互相替代。

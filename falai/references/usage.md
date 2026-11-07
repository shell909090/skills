# falai 配置与用法

以下命令在技能目录执行；从其他位置调用时将脚本路径替换为本技能的绝对路径。

## 初始化

由操作者取得服务凭证，以以下 JSON 字段保存为 `~/.config/agent/auth/falai.json.gpg`。字段名不是环境变量注入入口；脚本仅使用该 GPG 文件。

```json
{"FALAI_API_KEY": "YOUR_FALAI_API_KEY"}
```

在 fal.ai 控制台创建 API Key，选择任务所需权限；余额查询可能需要额外权限。

由操作者用自己的 GPG 公钥加密 JSON；可用 Emacs 编辑加密文件。不要把实际值交给助手或保存到仓库。GPG 根据密文选择私钥，无需硬编码公钥指纹。

## 余额

查询当前 Key 所属 workspace 的可用预付 credits：

```bash
python3 scripts/falai.py balance
```

该接口要求 `billing:usage:read` 权限；官方列出的包含此权限的 Key 预设为 `BILLING`、`READONLY`、`FULL`。返回 `credits.current_balance` 和 `credits.currency`。余额是可用于 fal.ai 服务的 credits，不代表可提现现金。

权限应以目标接口文档和控制台配置为准。参见[官方余额接口文档](https://fal.ai/docs/platform-apis/v1/account/billing.md)。

## Key 更新与认证排查

- `401 / Invalid API key`：当前凭证未通过认证，核对是否已更新到本机、是否被撤销或过期。
- `403 / not permitted`：检查该 Key 是否具有目标接口要求的权限，不能据此判断 Key 整体失效。
- 使用 `python3 scripts/falai.py models --limit 1` 做只读验证；余额查询还需要额外权限。
- 脚本使用 `Authorization: Key <完整密钥>`，无需因上述现象修改认证头。
- 允许脚本内部加载和解密凭证；不要直接调用 GPG 解密、查看或输出凭证内容。

## 查找模型

列出或搜索可用 model endpoint：

```bash
python3 scripts/falai.py models
python3 scripts/falai.py models "image to video" --limit 20
python3 scripts/falai.py models --category text-to-image --limit 50
```

响应包含 `models`、`next_cursor` 和 `has_more`。后续页面通过 `--cursor` 传入前一页的 `next_cursor`。

精确统计全部可用 endpoint 数量：

```bash
python3 scripts/falai.py models --count
```

fal.ai 不直接返回总数，`--count` 会自动遍历所有页面并按 `endpoint_id` 去重。这里统计的是模型 endpoint，不是去重后的底层模型家族。

## 模型输入

fal.ai 各模型的输入字段不同，应查看对应模型页面。HTTP 请求体直接使用模型输入对象，不要额外包裹 `input` 或 `arguments`。

小型输入可直接传 JSON：

```bash
python3 scripts/falai.py submit fal-ai/flux/schnell --data '{"prompt":"a mountain at sunrise"}'
```

较长输入放入普通 JSON 文件，或从标准输入传入：

```bash
python3 scripts/falai.py submit fal-ai/flux/schnell --input request.json
jq -n --arg prompt "a mountain at sunrise" '{prompt:$prompt}' | python3 scripts/falai.py submit fal-ai/flux/schnell --input -
```

模型 endpoint 使用完整路径，例如 `fal-ai/flux/schnell`。脚本只会向 fal.ai 固定域名发送认证请求，不接受任意 URL。

`--input` 不允许读取 `凭证目录` 或 `.gpg` 文件。除非明确需要 data URI，否则不要在模型输入中设置 `sync_mode: true`；该选项可能把媒体直接嵌入 JSON，造成输出过长。

## 队列推理

提交任务：

```bash
python3 scripts/falai.py submit <ENDPOINT> --input request.json
```

返回 JSON 中包含 `request_id`、`status_url`、`response_url` 和 `cancel_url` 等字段。后续命令使用 `request_id`，不要自行访问返回的 URL。

查询状态和日志：

```bash
python3 scripts/falai.py status <ENDPOINT> <REQUEST_ID>
python3 scripts/falai.py status <ENDPOINT> <REQUEST_ID> --logs
```

等待完成并获取结果：

```bash
python3 scripts/falai.py wait <ENDPOINT> <REQUEST_ID>
python3 scripts/falai.py wait <ENDPOINT> <REQUEST_ID> --interval 3 --timeout 900
```

单独获取已完成结果或取消任务：

```bash
python3 scripts/falai.py result <ENDPOINT> <REQUEST_ID>
python3 scripts/falai.py cancel <ENDPOINT> <REQUEST_ID>
```

`wait` 默认每 2 秒查询一次，最多等待 600 秒。队列状态可能是 `IN_QUEUE`、`IN_PROGRESS` 或 `COMPLETED`；`COMPLETED` 仍可能包含模型错误，脚本会单独检查。

## 同步推理

短任务可使用同步接口：

```bash
python3 scripts/falai.py run <ENDPOINT> --input request.json
python3 scripts/falai.py run <ENDPOINT> --data '{"prompt":"a mountain at sunrise"}' --timeout 300
```

长时间任务优先使用 `submit` 和 `wait`，避免单一 HTTP 连接超时。

## 输出和错误

- 成功时输出 fal.ai 原始 JSON 的紧凑格式。
- 图片、视频或音频结果通常包含临时 URL；需要长期保留时应及时下载。
- 输入校验失败通常返回 HTTP `422`；限流通常返回 `429`。
- 错误写到标准错误，并以非零状态码退出。

## 官方文档

- 认证：https://fal.ai/docs/documentation/setting-up/authentication/
- 队列：https://fal.ai/docs/documentation/model-apis/inference/queue/
- 同步推理：https://fal.ai/docs/documentation/model-apis/inference/synchronous/

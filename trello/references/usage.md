# trello 配置与用法

以下命令在技能目录执行；从其他位置调用时将脚本路径替换为本技能的绝对路径。

1. 打开 https://trello.com/apps/admin ，创建非 Power-Up app（如界面提供该类型），进入 OAuth 2.0，Security Type 选 Confidential。非 Power-Up app 没有 Power-Up 的单工作区限制。
2. 设置 Callback URL 为你控制的地址，并将完全相同的地址填入 redirect_uri。当前脚本采用手动粘贴完整回调 URL：该页面不需处理 code，但应避免第三方脚本、访问日志及外部跳转。若控制台允许 localhost，可用 http://localhost:8766/callback；授权后页面无法连接也可从地址栏复制 URL。
3. 勾选 read:member:trello、read:board:trello；需要修改卡片时再加 write:board:trello；读取工作区可加 read:organization:trello。保存后复制 Client ID 和 Client Secret。
4. 自行将下列 JSON 加密保存到 `~/.config/agent/auth/trello.json.gpg`（实际值不要发到对话，也不要作为 shell 参数）。gpg_recipient 是本机可用加密公钥的指纹，必须也能解密。

```json
{
  "client_id": "你的 Client ID",
  "client_secret": "你的 Client Secret",
  "redirect_uri": "与你注册的 Callback URL 完全一致",
  "scopes": ["read:member:trello", "read:board:trello", "write:board:trello"],
  "gpg_recipient": "你的 GPG 公钥指纹"
}
```

可由密码管理器/编辑器通过管道将 JSON 输入 `gpg --encrypt --recipient 公钥指纹 --output ~/.config/agent/auth/trello.json.gpg`。不要把明文保存在同步目录。

```bash
python3 scripts/trello.py login
python3 scripts/trello.py api GET '/members/me?fields=id,username'
python3 scripts/trello.py api GET '/members/me/boards?fields=id,name'
python3 scripts/trello.py api GET '/boards/BOARD_ID/lists'
python3 scripts/trello.py api GET '/lists/LIST_ID/cards'
# 只有用户要求写入时执行：
python3 scripts/trello.py api POST /cards --data '{"idList":"LIST_ID","name":"卡片标题"}'
```

login 输出授权链接，完成授权后在本地终端隐藏输入完整回调 URL。脚本验证 state，使用 PKCE 换取令牌。offline_access 自动加入；令牌仅在内存解密，刷新后原子加密写回同一文件。禁读/打印凭证文件或手工解密展示。路径前不加 /1。HTTP 错误不输出响应正文；失败写请求不会自动重试。

同一份凭证只由一个运行节点负责刷新：本机文件锁无法协调多台服务器，refresh token 会轮换。需确保 gpg-agent 可无人值守解密。刷新写回若失败，应重新 login。部署后可用 `workspace list` 和 `board list` 验证读取权限。

官方文档：
- https://developer.atlassian.com/cloud/trello/guides/rest-api/oauth-2-client-configuration/
- https://developer.atlassian.com/cloud/trello/guides/rest-api/oauth-2-confidential-client-usage/

## 常用资源命令

所有结果输出 JSON。对象用 ID 指定，不进行名称匹配。每级命令支持 `--help`。

```bash
python3 scripts/trello.py workspace list
python3 scripts/trello.py workspace show WORKSPACE_ID
python3 scripts/trello.py workspace boards WORKSPACE_ID
python3 scripts/trello.py workspace members WORKSPACE_ID
python3 scripts/trello.py board list --filter all
python3 scripts/trello.py board show BOARD_ID
python3 scripts/trello.py board lists BOARD_ID
python3 scripts/trello.py board cards BOARD_ID
python3 scripts/trello.py board members BOARD_ID
python3 scripts/trello.py board labels BOARD_ID
python3 scripts/trello.py list list BOARD_ID
python3 scripts/trello.py list show LIST_ID
python3 scripts/trello.py card list --board BOARD_ID
python3 scripts/trello.py card list --list LIST_ID --filter all
python3 scripts/trello.py card show CARD_ID
python3 scripts/trello.py card comments CARD_ID --limit 50
python3 scripts/trello.py card attachments CARD_ID
python3 scripts/trello.py card checklists CARD_ID
```

评论默认返回最近 50 条；用 `--before ACTION_ID` 获取更早一页，不能把单页当全部评论。
`board list`、`board lists/cards`、`card list` 默认 open；可选 `--filter all/closed`。

以下命令直接写入，Agent 仅在用户请求相应操作时使用。先查询核对 ID。

```bash
python3 scripts/trello.py board create --name '项目' --workspace WORKSPACE_ID
python3 scripts/trello.py board update BOARD_ID --name '新名称'
python3 scripts/trello.py list create --board BOARD_ID --name '待处理'
python3 scripts/trello.py list update LIST_ID --name '处理中'
python3 scripts/trello.py card create --list LIST_ID --name '任务' --description '说明'
python3 scripts/trello.py card update CARD_ID --description '更新说明' --due '2026-12-01T10:00:00Z'
python3 scripts/trello.py card update CARD_ID --due null --due-complete false
python3 scripts/trello.py card move CARD_ID --to-list LIST_ID
# 跨看板移动同时指定 --board DEST_BOARD_ID
python3 scripts/trello.py card comment CARD_ID --text '评论'
python3 scripts/trello.py card add-member CARD_ID MEMBER_ID
python3 scripts/trello.py card remove-member CARD_ID MEMBER_ID
python3 scripts/trello.py card add-label CARD_ID LABEL_ID
python3 scripts/trello.py card remove-label CARD_ID LABEL_ID
python3 scripts/trello.py card archive CARD_ID
python3 scripts/trello.py card unarchive CARD_ID
# 永久删除，不可恢复，仅在明确要求永久删除时使用
python3 scripts/trello.py card delete CARD_ID
```

board/list 同样支持 archive、unarchive。其他接口仍通过 api 调用。封装不额外提升 OAuth 权限。
建议先验证只读命令，再在专用测试看板上验证所需写操作。

认证更新使用本机排他锁：login 与 refresh 的读取、token 交换和加密写回串行执行。业务 API 请求及结果输出在释放锁后执行，不占用凭证锁。

---
name: coingecko
description: 使用 CoinGecko 查询加密货币价格、市值排行和币种详情；提供只读行情，不执行交易。
---

# CoinGecko

使用本技能的 `scripts/coingecko.py`。相对路径以本 SKILL.md 所在目录为基准，执行前取得技能绝对路径，不依赖调用者工作目录。

## 环境与身份

需要 Python 3 标准库、系统 CA 证书和网络连接，无额外 Python 依赖。当前脚本使用匿名公共 API，不读取凭证、不需要 GPG、不支持 Demo/Pro API key。匿名接口可用性和限流由服务端决定；认证失败时报告限制，不擅自切换付费接口。

## 使用

```bash
python3 scripts/coingecko.py --help
python3 scripts/coingecko.py price bitcoin ethereum
python3 scripts/coingecko.py markets --limit 20
python3 scripts/coingecko.py coin bitcoin
```

使用 CoinGecko coin ID，不把 BTC 等交易符号直接当作 ID。计价货币默认为 USD，可用 `--vs-currency` 调整价格和排行查询。全部操作只读。

参数、分页和输出见 [使用说明](references/usage.md)。行情是查询时取得的数据，可能经过缓存；报告时注明计价货币和查询时间，不当作实时成交价。返回缺失字段或空对象不代表价格为零。

列表默认仅一页，不把它当作完整市场。收到限流时停止高频查询，按服务端提示等待，不无限重试。不要为普通行情查询创建账户或购买额度。

# CoinGecko 使用说明

以下命令相对技能目录运行；也可使用脚本的绝对路径。脚本调用 `https://api.coingecko.com/api/v3` 的匿名接口。本文不保证匿名访问永久可用；Demo/Pro 认证属于不同配置方式，当前脚本未实现。

## 简单价格

```bash
python3 scripts/coingecko.py price bitcoin ethereum
python3 scripts/coingecko.py price bitcoin --vs-currency cny
```

参数使用 coin ID，例如 `bitcoin`、`ethereum`，而不是 `BTC`、`ETH`。支持一次查询多个 ID，避免逐币重复请求。

## 市值排行

```bash
python3 scripts/coingecko.py markets
python3 scripts/coingecko.py markets --limit 50 --page 2 --vs-currency cny
python3 scripts/coingecko.py markets --sparkline
```

按市值降序返回；`--limit` 为每页数量，范围 1–250，默认 20；`--page` 默认 1，脚本允许 1–1000。需要更多结果时递增页码，达到用户要求数量或返回空列表时停止。多页查询之间市场可能变化，不能保证一致性快照。

常用字段包括 `id`、`symbol`、`name`、`current_price`、`market_cap`、`market_cap_rank`、`total_volume`、`price_change_percentage_24h` 和 `last_updated`。按实际返回值处理缺失或 null 字段。

## 币种详情

```bash
python3 scripts/coingecko.py coin bitcoin
```

返回币种详情原始 JSON，不修改或交易资产。

## 输出、验证与错误

先运行 `--help` 检查入口，再用 `price bitcoin` 做一次只读联网验证。成功时 stdout 输出紧凑 JSON。HTTP 错误、连接错误或超时通常向 stderr 输出 JSON 错误并以非零状态退出；网络超时设为 30 秒。不自动重试，不创建本地缓存或输出文件。

认证失败或限流时保留状态码并说明原因。不要将失败请求、空结果或缺失字段解释为行情值。上游返回非 JSON 等异常也可能使脚本退出，不应声称查询成功。

## 官方接口参考

- [CoinGecko 文档](https://docs.coingecko.com/)
- [市值排行及分页参数](https://docs.coingecko.com/reference/coins-markets)（该页面为 Pro 文档；认证与额度不适用于本脚本的匿名调用）

# amap 配置与用法

以下命令在技能目录执行；从其他位置调用时将脚本路径替换为本技能的绝对路径。

## 初始化

由操作者取得服务凭证，以以下 JSON 字段保存为 `~/.config/agent/auth/amap.json.gpg`。字段名不是环境变量注入入口；脚本仅使用该 GPG 文件。

```json
{"AMAP_API_KEY": "YOUR_AMAP_API_KEY"}
```

在高德开放平台为应用申请 Web 服务 Key。

由操作者用自己的 GPG 公钥加密 JSON；可用 Emacs 编辑加密文件。不要把实际值交给助手或保存到仓库。GPG 根据密文选择私钥，无需硬编码公钥指纹。

### 地理编码

`geocode` 用于街道、门牌号等地址，不用于搜索餐馆、酒店或景点名称。该子命令只支持 `--city`，不支持 `--extensions`：

```bash
python3 scripts/amap.py geocode "北京市天安门"
python3 scripts/amap.py geocode "黑山头镇" --city 额尔古纳市
```

### POI 搜索

餐馆、酒店、商店、景点等地点名称使用 `search`：

```bash
python3 scripts/amap.py search "得意楼蒸菜馆" --city 常熟市 --city-limit
python3 scripts/amap.py search "咖啡馆" --city 北京市 --limit 10 --page 1
python3 scripts/amap.py search "故宫博物院" --city 北京市 --extensions all
```

`search` 支持 `--city`、`--city-limit`、`--limit`、`--page` 和 `--extensions base|all`。`--city-limit` 将结果严格限制在指定城市；`--limit` 范围为 1 到 25。

### 地址歧义

简称或同名地点可能被高德匹配到错误城市。例如“黑山头”可能匹配到新疆，而不是呼伦贝尔的额尔古纳市。已知城市时，应优先使用完整地址，或通过 `--city` 限定城市；不要仅凭模糊地名直接进行路线规划。

### 路线规划

坐标格式为 `经度,纬度`：

```bash
python3 scripts/amap.py driving "116.397428,39.90923" "116.481499,39.990475"
python3 scripts/amap.py driving "116.397428,39.90923" "116.481499,39.990475" --extensions all
python3 scripts/amap.py transit "116.397428,39.90923" "116.481499,39.990475" --city 010
python3 scripts/amap.py walking "116.397428,39.90923" "116.481499,39.990475"
```

只有 `driving` 支持 `--extensions base|all`。`transit` 和 `walking` 不支持 `--extensions`。公交路线的 `--city` 为起点城市或城市编码；跨城时可使用 `--cityd` 指定终点城市。

所有选项必须写在对应子命令之后。例如使用 `python3 scripts/amap.py search "故宫" --extensions all`，不要写成 `python3 scripts/amap.py --extensions all search "故宫"`。

成功时返回高德 API 原始 JSON 的紧凑格式。错误信息写到标准错误并以非零状态码退出；脚本不会输出 API Key。

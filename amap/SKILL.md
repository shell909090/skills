---
name: amap
description: 使用高德地图查询地址坐标、搜索地点，以及规划驾车、公交或步行路线。
---

# amap

使用本技能的 `scripts/amap.py`。相对路径以本 SKILL.md 所在目录为基准，不依赖调用者当前目录；执行前取得技能绝对路径，或切换到技能目录。

## 身份与运行环境

凭证固定为 `~/.config/agent/auth/amap.json.gpg`，允许 auth 目录是软链接。不得直接展示或手工解密凭证；仅让脚本内部加载。缺失时按[配置与用法](references/usage.md)指导操作者初始化，不搜索其他目录。

需要 Python 3.9+、GnuPG 及运行用户可用的解密私钥。

## 使用

先查看帮助或执行只读验证：

```bash
python3 scripts/amap.py --help
python3 scripts/amap.py geocode "北京市天安门"
```

地点名称用 search，街道地址用 geocode；已知城市时限定 --city。坐标顺序是经度、纬度。

具体命令、字段、分页和错误处理见[配置与用法](references/usage.md)，根据当前操作读取相关部分。请求失败时报告错误，不通过输出凭证排查；写请求失败不应盲目重复提交。

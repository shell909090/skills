#!/usr/bin/env python3
"""opencode-go.py — 查询 OpenCode Go 订阅的额度使用率与重置时间。

用法:
  opencode-go.py           # 人类可读：每个窗口的使用率 + 重置时间
  opencode-go.py --json    # 服务器原始 JSON，便于其他脚本消费

凭证: gpg 解密统一目录中的
      配置的 opencode-go.json.gpg 的 OPENCODE_GO_API_KEY 字段。
      key 只在内存中使用，不打印、不落盘、不写缓存。
      这把 key 只用于读 usage，不要拿去做推理或别的调用。

退出码: 0 成功; 2 凭证缺失; 3 请求或解析失败。
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API_URL = "https://opencode.ai/zen/go/v1/usage"
KEY_ENV = "OPENCODE_GO_API_KEY"
CREDENTIALS_FILE = Path.home() / ".config" / "agent" / "auth" / "opencode-go.json.gpg"
# 人类可读输出使用固定显示时区；JSON 保留服务端时间。
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
WINDOWS = (("rolling", "5h"), ("weekly", "week"), ("monthly", "month"))


def die(msg: str, code: int) -> None:
    """错误统一走 stderr 并给出约定退出码。"""
    print(msg, file=sys.stderr)
    sys.exit(code)


def load_key() -> str:
    """从统一 GPG 文件读取凭证，不回显值。"""
    if not CREDENTIALS_FILE.exists():
        die(f"缺少凭证：{CREDENTIALS_FILE}；请按技能配置说明创建加密 JSON。", 2)

    try:
        result = subprocess.run(
            ["gpg", "--quiet", "--decrypt",
             str(CREDENTIALS_FILE)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
        )
    except FileNotFoundError:
        die(f"错误：系统未安装 gpg。", 2)
    except subprocess.TimeoutExpired:
        die("错误：gpg 解密超时。", 2)

    if result.returncode != 0:
        die("错误：gpg 解密失败（没有对应私钥，或文件已损坏）。", 2)

    try:
        creds = json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        die("错误：解密后的内容不是合法 UTF-8 JSON。", 2)

    token = creds.get(KEY_ENV) if isinstance(creds, dict) else None
    if not isinstance(token, str) or not token.strip():
        die(f"错误：凭据文件里缺少 {KEY_ENV} 字段。", 2)
    return token.strip()


def fetch(key: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(API_URL, headers={
        "Authorization": f"Bearer {key}",
        "User-Agent": "opencode-go/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        die(f"错误：HTTP {exc.code} {body}"
            f"（key 失效、订阅未生效，或端点已变更）", 3)
    except urllib.error.URLError as exc:
        die(f"错误：网络不可达（{exc.reason}）", 3)
    except ValueError:
        die("错误：响应不是合法 JSON（端点可能已改版）", 3)


def fmt_reset(iso: str) -> tuple[str, str]:
    """ISO 时间戳 -> (本地时间字符串, 相对剩余)。"""
    if not iso:
        return "未知", ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso, ""
    local = dt.astimezone(LOCAL_TZ)
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        rel = "已到期"
    else:
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins = rem // 60
        if days:
            rel = f"{days}d{hours}h 后"
        elif hours:
            rel = f"{hours}h{mins}m 后"
        else:
            rel = f"{mins}m 后"
    return local.strftime("%Y-%m-%d %H:%M"), rel


def main() -> None:
    ap = argparse.ArgumentParser(
        description="查询 OpenCode Go 订阅的额度使用率与重置时间")
    ap.add_argument("--json", action="store_true", help="输出服务器原始 JSON")
    args = ap.parse_args()

    data = fetch(load_key())

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    usage = data.get("usage")
    if not isinstance(usage, dict) or not usage:
        die(f"错误：响应里没有 usage 字段："
            f"{json.dumps(data, ensure_ascii=False)[:200]}", 3)

    stamp = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")
    print(f"OpenCode Go 用量（{stamp}）")
    for name, label in WINDOWS:
        win = usage.get(name)
        if not isinstance(win, dict):
            continue
        pct = win.get("percent")
        pct_s = f"{pct:g}%" if isinstance(pct, (int, float)) else "?"
        when, rel = fmt_reset(win.get("resetsAt"))
        status = win.get("status") or "ok"
        line = f"  {label:<5}{pct_s:>4}  重置 {when}（{rel}）"
        if status != "ok":
            line += f"  [{status}]"
        print(line)


if __name__ == "__main__":
    main()

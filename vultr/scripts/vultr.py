#!/usr/bin/env python3
"""Vultr OAuth、账户流量及账单查询。"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_URL = "https://api.vultr.com"
USER_AGENT = "agent-vultr-usage/0.1"
REFRESH_MARGIN = 120
LOCAL_TZ = datetime.now().astimezone().tzinfo
GIB = 1024 ** 3


def die(msg, code):
    print(msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- HTTP

def api_get(key, path, params=None, timeout=30):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    for attempt in (1, 2):
        try:
            with OPENER.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = "（响应正文已隐藏）"
            if exc.code == 429 and attempt == 1:
                wait = exc.headers.get("Retry-After") or "5"
                try:
                    time.sleep(max(0, min(float(wait), 30)))
                except ValueError:
                    time.sleep(5)
                continue
            if exc.code == 401:
                die(f"错误：HTTP 401 OAuth token 无效或权限不足（{path}）：{body}", 3)
            if exc.code == 403:
                die(f"错误：HTTP 403 该 token 无权访问 {path}（IP 白名单或权限范围？）：{body}", 3)
            if exc.code == 404:
                die(f"错误：HTTP 404 {path} 不存在（端点可能已变更）：{body}", 3)
            die(f"错误：HTTP {exc.code} {path}：{body}", 3)
        except urllib.error.URLError as exc:
            die(f"错误：网络不可达（{exc.reason}）", 3)
        except ValueError:
            die(f"错误：{path} 返回的不是合法 JSON。", 3)


def api_list(key, path, params=None, max_pages=40, want=None):
    """跟随 meta.links.next 翻页，返回 (items, list_key)。

    want: 只要前 want 条就停。翻页是每页一次 HTTP 请求，为了取最新 3 条账单
    去把几十页全翻完会白等几十秒（Vultr 每请求约 1s）。
    """
    items = []
    cursor = None
    list_key = None
    for _ in range(max_pages):
        page_params = dict(params or {})
        page_params.setdefault("per_page", 100)
        if cursor:
            page_params["cursor"] = cursor
        data = api_get(key, path, page_params)
        if list_key is None:
            list_key = next((k for k, v in data.items() if isinstance(v, list)), None)
            if list_key is None:
                die(f"错误：{path} 响应里找不到列表字段：{json.dumps(data)[:200]}", 3)
        items.extend(data.get(list_key) or [])
        if want is not None and len(items) >= want:
            break
        cursor = ((data.get("meta") or {}).get("links") or {}).get("next") or None
        if not cursor:
            break
    else:
        die("错误：分页达到上限，结果不完整。", 3)
    return items, list_key


# ---------------------------------------------------------------- 格式化

def gb(num_gib, unit="GiB"):
    if num_gib is None:
        return "?"
    return f"{num_gib:,.1f} {unit}"


def short_date(value):
    """时间戳转成日期。Vultr 的带宽周期用 epoch 秒，账单用 ISO 字符串。"""
    if value in (None, ""):
        return "?"
    text = str(value)
    if text.isdigit():                       # epoch 秒
        try:
            return datetime.fromtimestamp(int(text), LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return text
    if len(text) >= 10 and text[4] == "-":   # ISO 8601
        return text[:10]
    return text


def money(value):
    if value is None:
        return "?"
    return f"${value:,.2f}"


def pct(part, whole):
    if not whole:
        return "?"
    return f"{part / whole * 100:.1f}%"


def stamp():
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")


def quota_of(period):
    """流量配额由实例额度 + 赠送额度 + 购买额度构成。"""
    return sum((period.get(k) or 0) for k in
               ("instance_bandwidth_credits", "free_bandwidth_credits",
                "purchased_bandwidth_credits"))


def period_block(title, period):
    out_gb = period.get("gb_out") or 0
    quota = quota_of(period)
    lines = [f"  {title}",
             f"    出站 {gb(out_gb)} / 配额 {gb(quota)}（{pct(out_gb, quota)}）",
             f"    入站 {gb(period.get('gb_in') or 0)}"]
    detail = (f"    配额构成：实例 {period.get('instance_bandwidth_credits') or 0} + "
              f"赠送 {period.get('free_bandwidth_credits') or 0} + "
              f"购买 {period.get('purchased_bandwidth_credits') or 0} GiB")
    lines.append(detail)
    lines.append(f"    实例 {period.get('total_instance_count')} 台 / "
                 f"{period.get('total_instance_hours')} 机时")
    overage = period.get("overage")
    if overage is not None:
        lines.append(f"    超额 {overage} GB × ${period.get('overage_unit_cost') or 0:g}/GB"
                     f" = {money(period.get('overage_cost'))}")
    span = (f"{short_date(period.get('timestamp_start'))} → "
            f"{short_date(period.get('timestamp_end'))}")
    lines.append(f"    区间 {span}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 子命令

def cmd_summary(key, as_json):
    account = api_get(key, "/v2/account").get("account") or {}
    bandwidth = api_get(key, "/v2/account/bandwidth").get("bandwidth") or {}
    charges, _ = api_list(key, "/v2/billing/pending-charges")

    if as_json:
        print(json.dumps({"account": account, "bandwidth": bandwidth,
                          "pending_charges": charges}, ensure_ascii=False, indent=2))
        return

    # Vultr 的 balance 是「可用信用额度」取负号：-balance 才是账户里还剩多少钱。
    balance = account.get("balance")
    print(f"Vultr 账户（{stamp()}）")
    raw = f"{balance:.2f}" if isinstance(balance, (int, float)) else balance
    print(f"  余额        {money(-balance if balance is not None else None)}"
          f"  （API balance={raw}）")
    print(f"  待扣费用    {money(account.get('pending_charges'))}")
    if account.get("last_payment_date"):
        paid = account.get("last_payment_amount")
        print(f"  上次充值    {money(abs(paid) if paid is not None else None)} "
              f"于 {short_date(account.get('last_payment_date'))}")

    current = bandwidth.get("current_month_to_date") or {}
    previous = bandwidth.get("previous_month") or {}
    projected = bandwidth.get("current_month_projected") or {}
    print()
    print("流量")
    if current:
        print(period_block("本月（current_month_to_date）", current))
    if previous:
        print(period_block("上月（previous_month）", previous))
    if projected:
        print(f"  预计（current_month_projected）出站 "
              f"{gb(projected.get('gb_out') or 0)}"
              f"，超额费用 {money(projected.get('overage_cost'))}")

    if charges:
        total = sum(float(item.get("total") or 0) for item in charges)
        print()
        print(f"费用构成（本账期 pending charges 共 {len(charges)} 项，合计 {money(total)}）")
        by_product = {}
        for item in charges:
            product = item.get("product") or "（未标注）"
            bucket = by_product.setdefault(product, [0.0, 0])
            bucket[0] += float(item.get("total") or 0)
            bucket[1] += 1
        for product, (amount, count) in sorted(by_product.items(), key=lambda kv: -kv[1][0]):
            print(f"  {product:<28} {money(amount):>10}  ({count} 项)")


def cmd_instances(key, as_json):
    instances, _ = api_list(key, "/v2/instances")
    rows = []
    for item in instances:
        iid = item.get("id")
        data = api_get(key, f"/v2/instances/{iid}/bandwidth").get("bandwidth") or {}
        incoming = sum(int(v.get("incoming_bytes") or 0) for v in data.values())
        outgoing = sum(int(v.get("outgoing_bytes") or 0) for v in data.values())
        rows.append({
            "id": iid,
            "label": item.get("label") or "",
            "region": item.get("region"),
            "plan": item.get("plan"),
            "status": item.get("status"),
            "allowed_bandwidth_gb": item.get("allowed_bandwidth"),
            "outgoing_bytes": outgoing,
            "incoming_bytes": incoming,
            "days": len(data),
        })

    if as_json:
        print(json.dumps({"instances": rows}, ensure_ascii=False, indent=2))
        return

    print(f"Vultr 实例流量（{stamp()}，共 {len(rows)} 台）")
    if not rows:
        print("  没有实例。")
        return
    for row in sorted(rows, key=lambda r: -r["outgoing_bytes"]):
        out_gib = row["outgoing_bytes"] / GIB
        in_gib = row["incoming_bytes"] / GIB
        allowed = row["allowed_bandwidth_gb"] or 0
        if allowed:
            quota_txt = f"/ {gb(allowed)}（{pct(out_gib, allowed)}）"
        else:
            quota_txt = "（API 未给该机型单独额度，用量计入账户总额度）"
        print(f"  {(row['label'] or row['id'])[:22]:<22} 出站 {gb(out_gib)} "
              f"{quota_txt}  入站 {gb(in_gib)}")
        print(f"      {row['region']} / {row['plan']} / {row['status']} / "
              f"{row['days']} 天记录 / {row['id']}")


def cmd_charges(key, as_json):
    charges, _ = api_list(key, "/v2/billing/pending-charges")
    if as_json:
        print(json.dumps({"pending_charges": charges}, ensure_ascii=False, indent=2))
        return
    total = sum(float(item.get("total") or 0) for item in charges)
    print(f"Vultr 未出账费用（{stamp()}，{len(charges)} 项，合计 {money(total)}）")
    for item in sorted(charges, key=lambda i: -float(i.get("total") or 0)):
        print(f"  {money(item.get('total')):>9}  {item.get('units')} "
              f"{item.get('unit_type') or ''} × ${item.get('unit_price') or 0:g}"
              f"  {item.get('description')}")
        if item.get("start_date") or item.get("end_date"):
            print(f"             {short_date(item.get('start_date'))} → "
                  f"{short_date(item.get('end_date'))}  [{item.get('product') or '?'}]")


def cmd_history(key, as_json, limit):
    history, _ = api_list(key, "/v2/billing/history",
                          {"per_page": max(1, min(limit, 500))}, want=limit)
    history = history[:limit]
    if as_json:
        print(json.dumps({"billing_history": history}, ensure_ascii=False, indent=2))
        return
    print(f"Vultr 账单历史（最近 {len(history)} 条）")
    for item in history:
        amount = item.get("amount")
        kind = (item.get("type") or "").lower()
        # payment 是充值（用户掏钱进来，API 记负数）；invoice 是消费出账（API 记正数）。
        # 按用户视角：充值写成 +、消费写成 -。
        if amount is None:
            shown = "?"
        elif float(amount) == 0:
            shown = money(0)
        elif kind == "payment":
            shown = f"+{money(abs(amount))}"
        else:
            shown = f"-{money(abs(amount))}"
        label = {"payment": "充值", "invoice": "消费"}.get(kind, kind or "?")
        bal = item.get("balance")
        bal_txt = money(-bal) if bal is not None else "?"
        print(f"  {short_date(item.get('date'))}  {shown:>11}  {label}  "
              f"{item.get('description') or ''}  余额 {bal_txt}")


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(
        prog="vultr.py",
        description="查询 Vultr 账户的流量使用与费用数据")
    parser.add_argument("--json", action="store_true", help="输出服务器原始 JSON")
    # 子命令上也接受 --json；default=SUPPRESS 避免覆盖写在前面的 --json
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="输出服务器原始 JSON")
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("summary", parents=[common], help="总览：账户 + 流量 + 费用构成（默认）")
    subs.add_parser("instances", parents=[common], help="每台实例的流量")
    subs.add_parser("charges", parents=[common], help="本账期未出账费用明细")
    hist = subs.add_parser("history", parents=[common], help="已出账的账单历史")
    hist.add_argument("-n", "--limit", type=int, default=10, help="条数，默认 10")
    subs.add_parser("login", help="从 Console 授权回调换取并保存 OAuth token")
    subs.add_parser("refresh", help="检查有效期，必要时刷新")
    subs.add_parser("show", help="显示认证状态，不输出凭证")
    args = parser.parse_args()
    if args.command in ("login", "refresh", "show"):
        auth_command(args.command)
        return
    if args.command == "history" and args.limit < 1:
        parser.error("limit 必须为正数")

    key = access_token()
    command = args.command or "summary"

    if command == "summary":
        cmd_summary(key, args.json)
    elif command == "instances":
        cmd_instances(key, args.json)
    elif command == "charges":
        cmd_charges(key, args.json)
    elif command == "history":
        cmd_history(key, args.json, args.limit)




# OAuth storage: local temporary locks, keyed by resolved credential path.
import base64
import fcntl
import getpass
import hashlib
import tempfile
from contextlib import contextmanager

TOKEN_FILE = Path.home() / '.config' / 'agent' / 'auth' / 'vultr.json.gpg'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect())


@contextmanager
def store_lock(path):
    lockdir = Path(tempfile.gettempdir()) / ('vultr-' + str(os.getuid()))
    lockdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = lockdir / hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    die('等待凭证锁超时；请检查其他 Vultr 进程。', 2)
                time.sleep(0.1)
        yield
    finally:
        os.close(fd)  # Never unlink: waiters must keep using the same inode.


def gpg(arguments, data=None):
    try:
        result = subprocess.run(['gpg', '--batch', '--quiet'] + arguments,
                                input=data, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        die('GPG 不可用或超时。', 2)
    if result.returncode:
        die('GPG 操作失败，请检查私钥、加密接收者和 gpg-agent。', 2)
    return result.stdout


def load_store(path):
    if not path.is_file():
        die(f'缺少凭证：{TOKEN_FILE}；请按 references/usage.md 初始化。', 2)
    try:
        data = json.loads(gpg(['--decrypt', str(path)]))
    except (ValueError, UnicodeError):
        die('凭证不是合法 JSON。', 2)
    if not isinstance(data, dict):
        die('凭证必须为 JSON 对象。', 2)
    return data


def save_store(path, data):
    recipient = data.get('gpg_recipient')
    if not isinstance(recipient, str) or not recipient.strip():
        die('凭证缺少 gpg_recipient，请用 Emacs 添加自己的加密公钥指纹。', 2)
    ciphertext = gpg(['--encrypt', '--recipient', recipient],
                     json.dumps(data, ensure_ascii=False).encode())
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(ciphertext)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def token_request(store, form):
    for key in ('provider_id', 'client_id', 'client_secret'):
        if not isinstance(store.get(key), str) or not store[key]:
            die(f'凭证缺少 {key}。', 2)
    provider = urllib.parse.quote(store['provider_id'], safe='')
    basic = base64.b64encode((store['client_id'] + ':' + store['client_secret']).encode()).decode()
    req = urllib.request.Request(BASE_URL + '/v2/oidc/provider/' + provider + '/token',
        data=urllib.parse.urlencode(form).encode(), headers={
            'Authorization': 'Basic ' + basic,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'})
    try:
        with OPENER.open(req, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        die('Token 请求失败，结果可能不确定；不要重试旧 refresh token，请重新 login。', 3)
    if (not isinstance(payload, dict)
            or not isinstance(payload.get('access_token'), str) or not payload['access_token']
            or not isinstance(payload.get('refresh_token'), str) or not payload['refresh_token']
            or not isinstance(payload.get('expires_in'), (int, float)) or payload['expires_in'] <= 0):
        die('Token 响应字段不完整，请重新 login。', 3)
    updated = dict(store)
    updated.update({key: payload[key] for key in ('access_token', 'refresh_token')})
    updated.update(expires_at=time.time() + payload['expires_in'], token_type='Bearer',
                   last_refresh=datetime.now().astimezone().isoformat())
    updated.pop('refresh_pending', None)
    return updated


def fresh(store):
    return (isinstance(store.get('access_token'), str) and bool(store['access_token'])
            and isinstance(store.get('expires_at'), (int, float))
            and store['expires_at'] > time.time() + REFRESH_MARGIN)


def access_token():
    path = TOKEN_FILE.resolve()  # Preserve directory AND individual-file symlinks.
    if not path.is_file():
        die(f'缺少 {TOKEN_FILE}，请先初始化。', 2)
    with store_lock(path):
        store = load_store(path)  # Re-read only after acquiring the lock.
        if store.get('refresh_pending'):
            die('上次刷新未确认完成；禁止重用旧 refresh token，请重新 login。', 2)
        if not fresh(store):
            if not store.get('refresh_token'):
                die('没有 refresh_token，请先 login。', 2)
            # Durable intent also preflights encryption and atomic writing before rotation.
            store['refresh_pending'] = True
            save_store(path, store)
            store = token_request(store, {'grant_type': 'refresh_token',
                                         'refresh_token': store['refresh_token']})
            save_store(path, store)
        return store['access_token']


def callback_code(raw, callback):
    parsed = urllib.parse.urlsplit(raw)
    expected = urllib.parse.urlsplit(callback)
    if ((parsed.scheme, parsed.netloc, parsed.path) !=
            (expected.scheme, expected.netloc, expected.path) or parsed.fragment):
        die('回调 URL 与凭证中的 callback 不匹配。', 2)
    query = urllib.parse.parse_qs(parsed.query)
    if 'error' in query or len(query.get('code', [])) != 1:
        die('授权失败或回调缺少唯一 code。', 2)
    return query['code'][0]


def auth_command(command):
    if command == 'refresh':
        access_token()
        print('凭证已检查并在需要时刷新。')
        return
    path = TOKEN_FILE.resolve()
    if not path.is_file():
        die(f'缺少 {TOKEN_FILE}，请按 references/usage.md 初始化。', 2)
    if command == 'login':
        initial = load_store(path)
        callback = initial.get('callback')
        if not isinstance(callback, str) or urllib.parse.urlsplit(callback).scheme not in ('http', 'https'):
            die('凭证缺少合法 callback URL。', 2)
        print('在 Vultr Console 的 OAuth Applications 中选择你的应用并授权。')
        print('回调必须与凭证的 callback 完全一致；无需本机监听。')
        print('浏览器跳转后，复制完整 URL 到下面的隐藏输入（不要贴到对话中）。')
        if not sys.stdin.isatty():
            die('login 需要交互终端，以隐藏回调 URL 输入。', 2)
        code = callback_code(getpass.getpass('完整回调 URL: '), callback)
        with store_lock(path):
            store = load_store(path)
            if any(store.get(k) != initial.get(k) for k in ('client_id', 'client_secret', 'provider_id', 'callback')):
                die('等待期间应用配置已改变，请重新 login。', 2)
            save_store(path, store)  # Preflight before consuming the one-time code.
            updated = token_request(store, {'grant_type': 'authorization_code',
                                           'code': code, 'redirect_url': callback})
            save_store(path, updated)
        print('OAuth 凭证已加密保存。')
        return
    # Atomic replacement yields a complete old or new snapshot; no writer lock needed.
    store = load_store(path)
    print(json.dumps({'has_access_token': bool(store.get('access_token')),
                      'has_refresh_token': bool(store.get('refresh_token')),
                      'expires_at': store.get('expires_at'),
                      'refresh_pending': bool(store.get('refresh_pending'))}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, EOFError):
        die('操作失败；请检查文件权限、网络或数据格式。凭证写入失败后请运行 show 检查状态。', 3)
    except KeyboardInterrupt:
        die('已取消；若刷新曾开始，请运行 show 检查状态。', 130)

#!/usr/bin/env python3
"""Small Mastodon REST API client."""

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


USER_AGENT = "agent-mastodon-api/0.1"
API_PAGE_LIMIT = 40
MAX_PAGES = 10
CREDENTIALS_FILE = Path.home() / ".config" / "agent" / "auth" / "mastodon.json.gpg"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("p", "div", "li", "blockquote"):
            self.parts.append("\n")


def plain_text(value):
    parser = TextExtractor()
    parser.feed(value or "")
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text


def quote_text(value):
    text = plain_text(value)
    return "\n".join(f"> {line}" for line in text.splitlines()) if text else "> (no text)"


def account_name(account):
    acct = account.get("acct") or account.get("username") or "unknown"
    display_name = plain_text(account.get("display_name"))
    return f"@{acct}" + (f" ({display_name})" if display_name else "")


def status_markdown(status, index=None):
    entry = status
    booster = None
    if status.get("reblog"):
        booster = account_name(status.get("account", {}))
        status = status["reblog"]
    account = account_name(status.get("account", {}))
    heading = f"## {index}. {account}" if index is not None else f"# {account}"
    lines = [
        heading,
        "",
        f"Timeline ID: {entry.get('id', 'unknown')} | Type: {'reblog' if booster else 'original'}",
        f"Timeline account: {account_name(entry.get('account', {}))} | "
        f"Account ID: {entry.get('account', {}).get('id', 'unknown')}",
        f"Timeline created: {entry.get('created_at') or 'unknown'}",
        f"Status ID: {status.get('id', 'unknown')} | Author: {account} | "
        f"Author ID: {status.get('account', {}).get('id', 'unknown')}",
        f"Created: {status.get('created_at') or 'unknown'} | URL: {status.get('url') or status.get('uri') or 'unknown'}",
        f"Language: {status.get('language') or 'unknown'} | "
        f"Visibility: {status.get('visibility') or 'unknown'} | "
        f"Reply to: {status.get('in_reply_to_id') or 'none'} | "
        f"Sensitive: {str(status.get('sensitive', False)).lower()}",
    ]
    if status.get("spoiler_text"):
        lines.extend(("", "Content warning:", quote_text(status["spoiler_text"])))
    lines.extend(("", quote_text(status.get("content"))))
    if booster:
        lines.extend(("", f"Boosted by {booster}"))
    counts = (
        f"Replies: {status.get('replies_count', 0)} | "
        f"Boosts: {status.get('reblogs_count', 0)} | "
        f"Favorites: {status.get('favourites_count', 0)}"
    )
    lines.extend(("", counts))
    return "\n".join(lines)


def page_metadata(items):
    lines = [f"Item count: {len(items)}"]
    if isinstance(items, PagedResults):
        lines.extend((f"Pages fetched: {items.pages_fetched}", f"Stopped: {items.stop_reason}"))
        if items.cursor:
            option = "--next" if items.cursor_key == "max_id" else "--min-id"
            lines.append(f"Next: {option} {items.cursor}")
        if items.timeline:
            boosts = sum(bool(item.get("reblog")) for item in items)
            replies = sum(bool(item.get("in_reply_to_id")) and not item.get("reblog") for item in items)
            lines.append(f"Original posts (excluding replies): {len(items) - boosts - replies} | Replies: {replies} | Reblogs: {boosts}")
            counts = Counter(account_name(item.get("account", {})) for item in items)
            if counts:
                lines.extend(("", "By timeline account (including reblogs):"))
                lines.extend(f"- {account}: {count}" for account, count in counts.most_common())
    elif items and items[-1].get("id"):
        lines.append(f"Next page: --max-id {items[-1]['id']}")
    return "\n".join(lines)


def timeline_markdown(title, statuses, paginated=False):
    if not statuses:
        text = f"# {title}\n\nNo results."
        return f"{text}\n\n{page_metadata(statuses)}" if paginated else text
    items = [status_markdown(status, index) for index, status in enumerate(statuses, 1)]
    text = f"# {title}\n\n" + "\n\n".join(items)
    return f"{text}\n\n{page_metadata(statuses)}" if paginated else text


def format_markdown(args, result):
    if args.command == "verify":
        name = account_name(result)
        note = plain_text(result.get("note"))
        lines = [f"# {name}", "", result.get("url", "")]
        if note:
            lines.extend(("", quote_text(result.get("note"))))
        lines.extend(
            (
                "",
                f"Statuses: {result.get('statuses_count', 0)} | "
                f"Following: {result.get('following_count', 0)} | "
                f"Followers: {result.get('followers_count', 0)}",
            )
        )
        return "\n".join(lines)
    if args.command in ("home", "public", "tag"):
        if args.command == "tag":
            title = f"#{args.hashtag}"
        else:
            title = "Home timeline" if args.command == "home" else "Public timeline"
        return timeline_markdown(title, result, paginated=True)
    if args.command in ("status", "post"):
        return status_markdown(result)
    if args.command == "context":
        ancestors = timeline_markdown("Ancestors", result.get("ancestors", []))
        descendants = timeline_markdown("Replies", result.get("descendants", []))
        return f"{ancestors}\n\n{descendants}"
    if args.command == "notifications":
        if not result:
            return f"# Notifications\n\nNo results.\n\n{page_metadata(result)}"
        items = []
        for index, notification in enumerate(result, 1):
            account = account_name(notification.get("account", {}))
            lines = [
                f"## {index}. {notification.get('type', 'unknown')} - {account}",
                "",
                f"Notification ID: {notification.get('id', 'unknown')} | "
                f"Account ID: {notification.get('account', {}).get('id', 'unknown')}",
            ]
            if notification.get("created_at"):
                lines.extend(("", notification["created_at"]))
            if notification.get("status"):
                lines.extend(("", status_markdown(notification["status"])))
            items.append("\n".join(lines))
        return "# Notifications\n\n" + "\n\n".join(items) + f"\n\n{page_metadata(result)}"
    if args.command == "trends":
        title = f"Trending {args.type}"
        if args.type == "statuses":
            return timeline_markdown(title, result)
        sections = [f"# {title}"]
        for index, item in enumerate(result, 1):
            name = "#" + item.get("name", "") if args.type == "tags" else plain_text(item.get("title"))
            lines = [f"## {index}. {name}", "", item.get("url", "")]
            if item.get("description"):
                lines.extend(("", quote_text(item["description"])))
            for day in item.get("history", []):
                lines.append(f"Day: {day.get('day', '')} | Uses: {day.get('uses', 0)} | Accounts: {day.get('accounts', 0)}")
            sections.append("\n".join(lines))
        if not result:
            sections.append("No results.")
        return "\n\n".join(sections)
    if args.command == "search":
        sections = ["# Search results"]
        accounts = result.get("accounts", [])
        hashtags = result.get("hashtags", [])
        statuses = result.get("statuses", [])
        if accounts:
            sections.append("## Accounts\n\n" + "\n".join(
                f"- {account_name(account)} - {account.get('url', '')}" for account in accounts
            ))
        if hashtags:
            sections.append("## Hashtags\n\n" + "\n".join(
                f"- #{tag.get('name', '')} - {tag.get('url', '')}" for tag in hashtags
            ))
        if statuses:
            sections.append("## Statuses\n\n" + "\n\n".join(
                status_markdown(status, index) for index, status in enumerate(statuses, 1)
            ))
        if len(sections) == 1:
            sections.append("No results.")
        return "\n\n".join(sections)
    return "```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```"


def fail(message, detail=None):
    result = {"error": message}
    if detail is not None:
        result["detail"] = detail
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    raise SystemExit(1)


def decrypt_credentials():
    if not CREDENTIALS_FILE.is_file():
        fail("Missing credentials", {"path": str(CREDENTIALS_FILE), "action": "Create encrypted JSON as documented in this skill"})
    try:
        result = subprocess.run(
            [
                "gpg",
                "--quiet",
                "--decrypt",
                str(CREDENTIALS_FILE),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except FileNotFoundError:
        fail("Unable to load Mastodon credentials", {"reason": "gpg is not installed"})
    except subprocess.TimeoutExpired:
        fail("Unable to load Mastodon credentials", {"reason": "gpg decryption timed out"})

    if result.returncode != 0:
        fail("Unable to load Mastodon credentials", {"reason": "gpg decryption failed"})

    try:
        plaintext = result.stdout.decode("utf-8-sig")
        credentials = json.loads(plaintext)
    except UnicodeDecodeError:
        fail("Unable to load Mastodon credentials", {"reason": "decrypted file is not UTF-8"})
    except json.JSONDecodeError as error:
        fail(
            "Unable to load Mastodon credentials",
            {"reason": "decrypted file is not valid JSON", "line": error.lineno, "column": error.colno},
        )

    if not isinstance(credentials, dict):
        fail("Unable to load Mastodon credentials", {"reason": "decrypted JSON is not an object"})
    return credentials


def credentials():
    stored = decrypt_credentials()
    base_url = stored.get("MASTODON_BASE_URL", "")
    access_token = stored.get("ACCESS_TOKEN", "")

    missing = [
        name
        for name, value in (("MASTODON_BASE_URL", base_url), ("ACCESS_TOKEN", access_token))
        if not isinstance(value, str) or not value
    ]
    if missing:
        fail("Unable to load Mastodon credentials", {"reason": "required fields are missing", "fields": missing})
    return base_url.rstrip("/"), access_token


def request_json(method, path, params=None, form=None):
    base_url, access_token = credentials()
    url = f"{base_url}{path}"
    data = None
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    if form is not None:
        data = urlencode(form, doseq=True).encode()

    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
            **({"Content-Type": "application/x-www-form-urlencoded"} if data else {}),
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error)
        except (ValueError, json.JSONDecodeError):
            detail = {"message": error.reason}
        fail(f"Mastodon returned HTTP {error.code}", detail)
    except (URLError, TimeoutError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        fail("Mastodon request failed", {"message": str(reason)})


def add_paging_options(parser):
    parser.add_argument("--limit", type=total_limit, default=API_PAGE_LIMIT * MAX_PAGES, help="Total items to fetch automatically (1-400, default: 400; at most 10 API pages)")
    parser.add_argument("--next", "--max-id", dest="max_id", help="Continue reading older items from the previous Next cursor")
    parser.add_argument("--since-id")
    parser.add_argument("--min-id")


def total_limit(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    if number > API_PAGE_LIMIT * MAX_PAGES:
        raise argparse.ArgumentTypeError("requested limit requires more than 10 API pages; maximum is 400 items per call")
    return number


class PagedResults(list):
    def __init__(self, timeline):
        super().__init__()
        self.timeline = timeline
        self.pages_fetched = 0
        self.stop_reason = "page limit reached; more results may exist"
        self.cursor_key = "max_id"
        self.cursor = None


def request_pages(path, args, extra_params=None):
    params = paging(args)
    params.update(extra_params or {})
    if args.min_id is not None and args.max_id is not None:
        fail("--min-id and --max-id cannot be combined for automatic paging")
    result = PagedResults(timeline=args.command != "notifications")
    result.cursor_key = "min_id" if args.min_id is not None else "max_id"
    seen_ids = set()
    seen_cursors = {params[result.cursor_key]} if result.cursor_key in params else set()
    for _ in range(MAX_PAGES):
        params["limit"] = min(API_PAGE_LIMIT, args.limit - len(result))
        page = request_json("GET", path, params)
        result.pages_fetched += 1
        if not isinstance(page, list):
            fail("Expected a list from a paginated Mastodon endpoint")
        if not page:
            result.stop_reason = "empty page; no more results returned"
            result.cursor = None
            break
        fresh = []
        for item in page:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                fail("A paginated Mastodon item is missing a string ID")
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                fresh.append(item)
        if result.cursor_key == "min_id":
            result[0:0] = fresh
        else:
            result.extend(fresh)
        cursor = page[0 if result.cursor_key == "min_id" else -1]["id"]
        if not fresh or cursor in seen_cursors:
            result.stop_reason = "pagination made no progress; results may be incomplete"
            result.cursor = None
            break
        seen_cursors.add(cursor)
        result.cursor = cursor
        params[result.cursor_key] = cursor
        if len(result) >= args.limit:
            result.stop_reason = "requested item limit reached; more results may exist"
            break
    return result


def paging(args):
    return {
        key: value
        for key, value in (
            ("limit", args.limit),
            ("max_id", args.max_id),
            ("since_id", args.since_id),
            ("min_id", args.min_id),
        )
        if value is not None
    }


def build_parser():
    parser = argparse.ArgumentParser(prog="mastodon.py", description="Mastodon REST API")
    parser.add_argument("--json", action="store_true", help="Output the complete original JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("verify", help="Verify the access token and return the current account")

    home = commands.add_parser("home", help="Read the home timeline")
    add_paging_options(home)

    public = commands.add_parser("public", help="Read the public timeline")
    add_paging_options(public)
    public.add_argument("--local", action="store_true")

    tag = commands.add_parser("tag", help="Read a hashtag timeline")
    tag.add_argument("hashtag")
    add_paging_options(tag)

    trends = commands.add_parser("trends", help="Read trending tags, statuses, or links")
    trends.add_argument("--type", choices=("tags", "statuses", "links"), default="tags")
    trends.add_argument("--limit", type=int, choices=range(1, 41), default=None)
    trends.add_argument("--offset", type=int, default=0)

    search = commands.add_parser("search", help="Search accounts, hashtags, or statuses")
    search.add_argument("query")
    search.add_argument("--type", choices=("accounts", "hashtags", "statuses"), default="statuses")
    search.add_argument("--limit", type=int, choices=range(1, 41), default=20)
    search.add_argument("--resolve", action="store_true")

    status = commands.add_parser("status", help="Read one status")
    status.add_argument("id")

    context = commands.add_parser("context", help="Read a status conversation")
    context.add_argument("id")

    notifications = commands.add_parser("notifications", help="Read notifications")
    add_paging_options(notifications)

    post = commands.add_parser("post", help="Publish a status")
    post.add_argument("text")
    post.add_argument("--visibility", choices=("public", "unlisted", "private", "direct"), default="public")
    post.add_argument("--reply-to", dest="reply_to")

    return parser


def run(args):
    if args.command == "verify":
        return request_json("GET", "/api/v1/accounts/verify_credentials")
    if args.command == "home":
        return request_pages("/api/v1/timelines/home", args)
    if args.command == "public":
        return request_pages("/api/v1/timelines/public", args, {"local": "true"} if args.local else None)
    if args.command == "tag":
        return request_pages(f"/api/v1/timelines/tag/{quote(args.hashtag, safe='')}", args)
    if args.command == "trends":
        maximum = 40 if args.type == "statuses" else 20
        limit = args.limit if args.limit is not None else maximum // 2
        if not 1 <= limit <= maximum or args.offset < 0:
            fail(f"trends requires --limit between 1 and {maximum} and --offset >= 0")
        return request_json("GET", f"/api/v1/trends/{args.type}", {"limit": limit, "offset": args.offset})
    if args.command == "search":
        params = {"q": args.query, "type": args.type, "limit": args.limit}
        if args.resolve:
            params["resolve"] = "true"
        return request_json("GET", "/api/v2/search", params)
    if args.command == "status":
        return request_json("GET", f"/api/v1/statuses/{quote(args.id, safe='')}")
    if args.command == "context":
        return request_json("GET", f"/api/v1/statuses/{quote(args.id, safe='')}/context")
    if args.command == "notifications":
        return request_pages("/api/v1/notifications", args)
    if args.command == "post":
        form = {"status": args.text, "visibility": args.visibility}
        if args.reply_to:
            form["in_reply_to_id"] = args.reply_to
        return request_json("POST", "/api/v1/statuses", form=form)
    fail(f"Unsupported command: {args.command}")


def main():
    argv = sys.argv[1:]
    json_output = "--json" in argv
    args = build_parser().parse_args([argument for argument in argv if argument != "--json"])
    result = run(args)
    if json_output:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        if isinstance(result, PagedResults):
            print(page_metadata(result), file=sys.stderr)
    else:
        print(format_markdown(args, result))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read-only CoinGecko public API client."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
USER_AGENT = "agent-skills-coingecko/0.1"


def request_json(path, params=None):
    url = f"{COINGECKO_BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error)
        except (ValueError, json.JSONDecodeError):
            detail = {"message": error.reason}
        fail(f"CoinGecko returned HTTP {error.code}", detail)
    except (URLError, TimeoutError) as error:
        fail("CoinGecko request failed", {"message": str(error.reason if isinstance(error, URLError) else error)})


def fail(message, detail=None):
    result = {"error": message}
    if detail is not None:
        result["detail"] = detail
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    raise SystemExit(1)


def add_currency_option(parser):
    parser.add_argument("--vs-currency", default="usd", help="Quote currency, e.g. usd or cny")


def build_parser():
    parser = argparse.ArgumentParser(prog="coingecko.py", description="CoinGecko public API")
    commands = parser.add_subparsers(dest="command", required=True)

    markets = commands.add_parser("markets", help="Top coins by market cap")
    add_currency_option(markets)
    markets.add_argument("--limit", type=int, default=20, choices=range(1, 251))
    markets.add_argument("--page", type=int, default=1, choices=range(1, 1001))
    markets.add_argument("--sparkline", action="store_true")

    coin = commands.add_parser("coin", help="Details for one coin")
    coin.add_argument("id", help="CoinGecko coin id, e.g. bitcoin")

    price = commands.add_parser("price", help="Simple prices for one or more coins")
    price.add_argument("ids", nargs="+", help="CoinGecko coin ids")
    add_currency_option(price)

    return parser


def run(args):
    if args.command == "markets":
        return request_json(
            "/coins/markets",
            {
                "vs_currency": args.vs_currency,
                "order": "market_cap_desc",
                "per_page": args.limit,
                "page": args.page,
                "sparkline": str(args.sparkline).lower(),
            },
        )
    if args.command == "coin":
        return request_json(f"/coins/{args.id}")
    if args.command == "price":
        return request_json(
            "/simple/price",
            {"ids": ",".join(args.ids), "vs_currencies": args.vs_currency},
        )
    fail(f"Unsupported command: {args.command}")


def main():
    args = build_parser().parse_args()
    print(json.dumps(run(args), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

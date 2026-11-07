#!/usr/bin/env python3
"""Small client for the Amap Web Service API."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://restapi.amap.com/v3"
USER_AGENT = "agent-amap-api/0.1"
CREDENTIALS_FILE = Path.home() / ".config" / "agent" / "auth" / "amap.json.gpg"


def fail(message, detail=None):
    result = {"error": message}
    if detail is not None:
        result["detail"] = detail
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    raise SystemExit(1)


def api_key():
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
        fail("Unable to load Amap credentials", {"reason": "gpg is not installed"})
    except subprocess.TimeoutExpired:
        fail("Unable to load Amap credentials", {"reason": "gpg decryption timed out"})

    if result.returncode != 0:
        fail("Unable to load Amap credentials", {"reason": "gpg decryption failed"})

    try:
        plaintext = result.stdout.decode("utf-8-sig")
        credentials = json.loads(plaintext)
    except UnicodeDecodeError:
        fail("Unable to load Amap credentials", {"reason": "decrypted file is not UTF-8"})
    except json.JSONDecodeError as error:
        fail(
            "Unable to load Amap credentials",
            {"reason": "decrypted file is not valid JSON", "line": error.lineno, "column": error.colno},
        )

    value = credentials.get("AMAP_API_KEY") if isinstance(credentials, dict) else None
    if not isinstance(value, str) or not value:
        fail("Unable to load Amap credentials", {"reason": "AMAP_API_KEY is missing"})
    return value


def request_json(path, params):
    params = {"key": api_key(), "output": "JSON", **params}
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        fail(f"Amap returned HTTP {error.code}", {"message": str(error.reason)})
    except (URLError, TimeoutError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        fail("Amap request failed", {"message": str(reason)})

    if result.get("status") != "1":
        detail = {key: result.get(key) for key in ("infocode", "info") if key in result}
        fail("Amap API request failed", detail or result)
    return result


def build_parser():
    parser = argparse.ArgumentParser(prog="amap.py", description="Amap Web Service API")
    commands = parser.add_subparsers(dest="command", required=True)

    geocode = commands.add_parser("geocode", help="Convert an address to coordinates")
    geocode.add_argument("address")
    geocode.add_argument("--city")

    search = commands.add_parser("search", help="Search for a point of interest")
    search.add_argument("keywords")
    search.add_argument("--city")
    search.add_argument("--city-limit", action="store_true")
    search.add_argument("--limit", type=int, choices=range(1, 26), default=20)
    search.add_argument("--page", type=int, choices=range(1, 101), default=1)
    search.add_argument("--extensions", choices=("base", "all"), default="base")

    driving = commands.add_parser("driving", help="Plan a driving route")
    driving.add_argument("origin", help="Origin as longitude,latitude")
    driving.add_argument("destination", help="Destination as longitude,latitude")
    driving.add_argument("--extensions", choices=("base", "all"), default="base")

    transit = commands.add_parser("transit", help="Plan a public transit route")
    transit.add_argument("origin", help="Origin as longitude,latitude")
    transit.add_argument("destination", help="Destination as longitude,latitude")
    transit.add_argument("--city", required=True, help="Origin city or city adcode")
    transit.add_argument("--cityd", help="Destination city or city adcode")

    walking = commands.add_parser("walking", help="Plan a walking route")
    walking.add_argument("origin", help="Origin as longitude,latitude")
    walking.add_argument("destination", help="Destination as longitude,latitude")

    return parser


def run(args):
    if args.command == "geocode":
        params = {"address": args.address}
        if args.city:
            params["city"] = args.city
        return request_json("/geocode/geo", params)
    if args.command == "search":
        params = {
            "keywords": args.keywords,
            "citylimit": str(args.city_limit).lower(),
            "offset": args.limit,
            "page": args.page,
            "extensions": args.extensions,
        }
        if args.city:
            params["city"] = args.city
        return request_json("/place/text", params)
    if args.command == "driving":
        return request_json(
            "/direction/driving",
            {"origin": args.origin, "destination": args.destination, "extensions": args.extensions},
        )
    if args.command == "transit":
        params = {"origin": args.origin, "destination": args.destination, "city": args.city}
        if args.cityd:
            params["cityd"] = args.cityd
        return request_json("/direction/transit/integrated", params)
    if args.command == "walking":
        return request_json("/direction/walking", {"origin": args.origin, "destination": args.destination})
    fail(f"Unsupported command: {args.command}")


def main():
    args = build_parser().parse_args()
    print(json.dumps(run(args), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

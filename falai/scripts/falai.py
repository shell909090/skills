#!/usr/bin/env python3
"""Dependency-free client for common fal.ai inference operations."""

import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


QUEUE_BASE_URL = "https://queue.fal.run"
SYNC_BASE_URL = "https://fal.run"
PLATFORM_BASE_URL = "https://api.fal.ai/v1"
STORAGE_BASE_URL = "https://rest.alpha.fal.ai"
USER_AGENT = "agent-falai-api/0.1"
CREDENTIALS_FILE = Path.home() / ".config" / "agent" / "auth" / "falai.json.gpg"
AUTH_DIR = CREDENTIALS_FILE.parent.resolve()
ENDPOINT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


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
        fail("Unable to load fal.ai credentials", {"reason": "gpg is not installed"})
    except subprocess.TimeoutExpired:
        fail("Unable to load fal.ai credentials", {"reason": "gpg decryption timed out"})

    if result.returncode != 0:
        fail("Unable to load fal.ai credentials", {"reason": "gpg decryption failed"})
    try:
        credentials = json.loads(result.stdout.decode("utf-8-sig"))
    except UnicodeDecodeError:
        fail("Unable to load fal.ai credentials", {"reason": "decrypted file is not UTF-8"})
    except json.JSONDecodeError as error:
        fail(
            "Unable to load fal.ai credentials",
            {"reason": "decrypted file is not valid JSON", "line": error.lineno, "column": error.colno},
        )

    value = credentials.get("FALAI_API_KEY") if isinstance(credentials, dict) else None
    if not isinstance(value, str) or not value:
        fail("Unable to load fal.ai credentials", {"reason": "FALAI_API_KEY is missing"})
    return value


def endpoint_path(endpoint):
    if not ENDPOINT_PATTERN.fullmatch(endpoint) or ".." in endpoint or endpoint.endswith("/"):
        fail("Invalid fal.ai endpoint", {"endpoint": endpoint})
    return "/".join(quote(part, safe="-._") for part in endpoint.split("/"))


def request_id_path(request_id):
    if not request_id or "/" in request_id:
        fail("Invalid fal.ai request ID")
    return quote(request_id, safe="-._")


def request_json(method, url, body=None, timeout=60):
    data = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Key {api_key()}",
        "User-Agent": USER_AGENT,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as error:
        payload = error.read()
        try:
            detail = json.loads(payload) if payload else {"message": error.reason}
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = {"message": error.reason}
        fail(f"fal.ai returned HTTP {error.code}", detail)
    except (URLError, TimeoutError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        fail("fal.ai request failed", {"message": str(reason)})

    if not payload:
        return {}
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("fal.ai returned an invalid JSON response")


def upload_file(path):
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        fail("Unable to read upload file", {"path": str(file_path)})
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    initiate = request_json(
        "POST",
        f"{STORAGE_BASE_URL}/storage/upload/initiate",
        {"file_name": file_path.name, "content_type": content_type},
    )
    upload_url = initiate.get("upload_url")
    file_url = initiate.get("file_url")
    if not isinstance(upload_url, str) or not isinstance(file_url, str):
        fail("fal.ai upload initialization returned an unexpected response", initiate)
    try:
        data = file_path.read_bytes()
        request = Request(upload_url, data=data, method="PUT", headers={"Content-Type": content_type})
        with urlopen(request, timeout=300) as response:
            response.read()
    except (OSError, HTTPError, URLError, TimeoutError) as error:
        fail("fal.ai file upload failed", {"message": str(error)})
    return {"file_url": file_url, "content_type": content_type, "size": len(data)}


def load_input(args):
    if args.data is not None:
        source = args.data
    else:
        try:
            if args.input == "-":
                source = sys.stdin.read()
            else:
                input_path = Path(args.input).expanduser().resolve()
                if input_path.suffix == ".gpg" or input_path == AUTH_DIR or AUTH_DIR in input_path.parents:
                    fail("Refusing to use a credential file as model input")
                source = input_path.read_text(encoding="utf-8")
        except OSError as error:
            fail("Unable to read model input", {"message": str(error)})
    try:
        value = json.loads(source)
    except json.JSONDecodeError as error:
        fail("Model input is not valid JSON", {"line": error.lineno, "column": error.colno})
    if not isinstance(value, dict):
        fail("Model input must be a JSON object")
    return value


def queue_url(endpoint, request_id=None, action=None):
    request_endpoint = endpoint
    if request_id is not None:
        parts = endpoint.split("/")
        if len(parts) > 2:
            request_endpoint = "/".join(parts[:2])
    url = f"{QUEUE_BASE_URL}/{endpoint_path(request_endpoint)}"
    if request_id is not None:
        url += f"/requests/{request_id_path(request_id)}"
    if action:
        url += f"/{action}"
    return url


def status(endpoint, request_id, logs=False):
    url = queue_url(endpoint, request_id, "status")
    if logs:
        url += "?" + urlencode({"logs": 1})
    return request_json("GET", url)


def wait_for_result(endpoint, request_id, logs, interval, timeout):
    deadline = time.monotonic() + timeout
    while True:
        state = status(endpoint, request_id, logs)
        current = state.get("status")
        if current == "COMPLETED":
            if state.get("error"):
                fail("fal.ai request completed with an error", state)
            return request_json("GET", queue_url(endpoint, request_id))
        if current not in ("IN_QUEUE", "IN_PROGRESS"):
            fail("fal.ai returned an unexpected queue status", state)
        if time.monotonic() >= deadline:
            fail("Timed out waiting for fal.ai request", {"request_id": request_id, "status": current})
        time.sleep(interval)


def list_models(args):
    params = {"limit": 100 if args.count else args.limit, "status": args.status}
    if args.query:
        params["q"] = args.query
    if args.category:
        params["category"] = args.category
    if args.cursor and not args.count:
        params["cursor"] = args.cursor

    if not args.count:
        return request_json("GET", f"{PLATFORM_BASE_URL}/models?{urlencode(params)}")

    endpoint_ids = set()
    cursor = None
    while True:
        if cursor:
            params["cursor"] = cursor
        payload = request_json("GET", f"{PLATFORM_BASE_URL}/models?{urlencode(params)}")
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            fail("fal.ai returned an unexpected model list response")
        endpoint_ids.update(
            model["endpoint_id"]
            for model in models
            if isinstance(model, dict) and isinstance(model.get("endpoint_id"), str)
        )
        if not payload.get("has_more"):
            return {"count": len(endpoint_ids), "status": args.status}
        cursor = payload.get("next_cursor")
        if not isinstance(cursor, str) or not cursor:
            fail("fal.ai model pagination did not return a cursor")


def add_input_options(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--data", help="Model input as a JSON object string")
    group.add_argument("--input", help="Path to a JSON file, or - for stdin")


def add_request_options(parser):
    parser.add_argument("endpoint", help="Model endpoint, e.g. fal-ai/flux/schnell")
    parser.add_argument("request_id")


def positive_float(value):
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def build_parser():
    parser = argparse.ArgumentParser(prog="falai.py", description="Common fal.ai inference operations")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("balance", help="Read the current account credit balance")

    models = commands.add_parser("models", help="Search or count available model endpoints")
    models.add_argument("query", nargs="?", help="Search model names, descriptions, and categories")
    models.add_argument("--category")
    models.add_argument("--status", choices=("active", "deprecated"), default="active")
    models.add_argument("--limit", type=positive_int, default=20)
    models.add_argument("--cursor")
    models.add_argument("--count", action="store_true", help="Traverse all pages and return only the count")

    upload = commands.add_parser("upload", help="Upload a local media file to fal.ai storage")
    upload.add_argument("path")

    submit = commands.add_parser("submit", help="Submit a request to the queue")
    submit.add_argument("endpoint")
    add_input_options(submit)

    check = commands.add_parser("status", help="Read queue status")
    add_request_options(check)
    check.add_argument("--logs", action="store_true")

    result = commands.add_parser("result", help="Fetch a completed result")
    add_request_options(result)

    cancel = commands.add_parser("cancel", help="Request cancellation")
    add_request_options(cancel)

    wait = commands.add_parser("wait", help="Wait for completion and fetch the result")
    add_request_options(wait)
    wait.add_argument("--logs", action="store_true")
    wait.add_argument("--interval", type=positive_float, default=2.0)
    wait.add_argument("--timeout", type=positive_float, default=600.0)

    synchronous = commands.add_parser("run", help="Run synchronous inference")
    synchronous.add_argument("endpoint")
    synchronous.add_argument("--timeout", type=positive_float, default=600.0)
    add_input_options(synchronous)
    return parser


def run(args):
    if args.command == "balance":
        return request_json("GET", f"{PLATFORM_BASE_URL}/account/billing?expand=credits")
    if args.command == "models":
        return list_models(args)
    if args.command == "upload":
        return upload_file(args.path)
    if args.command == "submit":
        return request_json("POST", queue_url(args.endpoint), load_input(args))
    if args.command == "status":
        return status(args.endpoint, args.request_id, args.logs)
    if args.command == "result":
        return request_json("GET", queue_url(args.endpoint, args.request_id))
    if args.command == "cancel":
        return request_json("PUT", queue_url(args.endpoint, args.request_id, "cancel"))
    if args.command == "wait":
        return wait_for_result(args.endpoint, args.request_id, args.logs, args.interval, args.timeout)
    if args.command == "run":
        url = f"{SYNC_BASE_URL}/{endpoint_path(args.endpoint)}"
        return request_json("POST", url, load_input(args), timeout=args.timeout)
    fail(f"Unsupported command: {args.command}")


def main():
    args = build_parser().parse_args()
    print(json.dumps(run(args), ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

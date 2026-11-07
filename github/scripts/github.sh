#!/usr/bin/env bash
set -euo pipefail
set +x

readonly CREDENTIALS_FILE="$HOME/.config/agent/auth/github.json.gpg"

if (($# == 0)); then
  printf '%s\n' 'Usage: github.sh <command> [arguments...]' >&2
  exit 2
fi

case "$1" in
  --help|-h|--version)
    exec gh "$@"
    ;;
  repo|issue|pr|run|workflow|release|search|status|label|discussion|ruleset|attestation)
    ;;
  *)
    printf 'github.sh: blocked gh command: %s\n' "$1" >&2
    exit 2
    ;;
esac

for command in gpg jq gh; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'github.sh: required command is not installed: %s\n' "$command" >&2
    exit 1
  fi
done

if [[ ! -f "$CREDENTIALS_FILE" ]]; then
  printf 'github.sh: missing credentials: %s; see references/usage.md for initialization\n' "$CREDENTIALS_FILE" >&2
  exit 1
fi

if ! GH_TOKEN="$(
  gpg --quiet --decrypt "$CREDENTIALS_FILE" 2>/dev/null |
    jq -er '.GH_TOKEN | select(type == "string" and length > 0)'
)"; then
  printf '%s\n' 'github.sh: unable to load GH_TOKEN' >&2
  exit 1
fi

export GH_TOKEN
export GH_HOST=github.com
export GH_PROMPT_DISABLED=1
export GH_PAGER=cat
export PAGER=cat
export GH_EDITOR=false
export GIT_EDITOR=false
export VISUAL=false
export EDITOR=false
export GH_BROWSER=false
export BROWSER=false
unset GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN

exec gh "$@"

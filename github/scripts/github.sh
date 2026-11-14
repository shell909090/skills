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
  dependabot)
    shift
    if [[ ${1:-} == --help || ${1:-} == -h ]]; then
      printf '%s\n' 'Usage: github.sh dependabot list --repo OWNER/REPO [--state STATE|all]' '       github.sh dependabot view NUMBER --repo OWNER/REPO' '       github.sh dependabot update NUMBER --repo OWNER/REPO --state STATE [--dismissed-reason REASON] [--dismissed-comment COMMENT]'
      exit 0
    fi
    action=${1:-}; [[ $# -eq 0 ]] || shift
    method=GET
    alert_number=
    case "$action" in
      list) ;;
      view|update)
        alert_number=${1:-}; [[ $# -eq 0 ]] || shift
        [[ $alert_number =~ ^[1-9][0-9]*$ ]] || { printf '%s\n' 'github.sh: expected alert number' >&2; exit 2; }
        [[ $action != update ]] || method=PATCH ;;
      *) printf '%s\n' 'github.sh: expected dependabot list, view or update' >&2; exit 2 ;;
    esac
    repo=
    fields=()
    state_given=false
    while (($#)); do
      [[ $# -ge 2 ]] || { printf '%s\n' 'github.sh: missing option value' >&2; exit 2; }
      case "$1" in
        --repo) repo=$2 ;;
        --state)
          state_given=true
          if [[ $action != list || $2 != all ]]; then fields+=(-f "state=$2"); fi ;;
        --dismissed-reason|--dismissed-comment)
          [[ $action == update ]] || { printf '%s\n' 'github.sh: dismissal fields require update' >&2; exit 2; }
          field=${1#--}; fields+=(-f "${field//-/_}=$2") ;;
        *) printf 'github.sh: unsupported argument: %s\n' "$1" >&2; exit 2 ;;
      esac
      shift 2
    done
    [[ $repo =~ ^[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+$ && ${repo#*/} != . && ${repo#*/} != .. ]] || { printf '%s\n' 'github.sh: expected --repo OWNER/REPO' >&2; exit 2; }
    endpoint="repos/$repo/dependabot/alerts"
    case "$action" in
      list)
        $state_given || fields+=(-f state=open)
        set -- api --method GET "$endpoint" --paginate -f per_page=100 "${fields[@]}" ;;
      view)
        if $state_given; then printf '%s\n' 'github.sh: view does not accept --state' >&2; exit 2; fi
        set -- api --method GET "$endpoint/$alert_number" ;;
      update)
        $state_given || { printf '%s\n' 'github.sh: update requires --state' >&2; exit 2; }
        set -- api --method "$method" "$endpoint/$alert_number" "${fields[@]}" ;;
    esac
    ;;
  repo|issue|pr|run|workflow|release|search|status|label|discussion|ruleset|attestation|api)
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

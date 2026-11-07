.DEFAULT_GOAL := help
PYTHON ?= python3
AGENTS_DIR ?= $(HOME)/.agents/skills
CLAUDE_DIR ?= $(HOME)/.claude/skills
export AGENTS_DIR CLAUDE_DIR
# Optional explicit profile config, otherwise HERMES_HOME/config.yaml.
export HERMES_CONFIG

.PHONY: help check install install-codex install-claude install-hermes uninstall hermes-config
.NOTPARALLEL: install
help:
	@echo 'make check | install | install-codex | install-claude | install-hermes | uninstall'
install: check install-codex install-claude install-hermes
hermes-config: install-hermes
check install-codex install-claude install-hermes uninstall:
	@$(PYTHON) scripts/install.py $@

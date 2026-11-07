.DEFAULT_GOAL := help
PYTHON ?= python3
AGENTS_DIR ?= $(HOME)/.agents/skills
CLAUDE_DIR ?= $(HOME)/.claude/skills
export AGENTS_DIR CLAUDE_DIR

.PHONY: help check install uninstall hermes-config
help:
	@echo 'make check | install | uninstall | hermes-config'
check install uninstall hermes-config:
	@$(PYTHON) scripts/install.py $@

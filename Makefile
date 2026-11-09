# agent-audit-kit: thin wrapper around bin/kit. Every target is idempotent.
# Run `make` or `make help` for usage.
KIT  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
K    := $(KIT)/bin/kit
NAME ?=
SOURCE ?=
REF ?=
MODE ?= eval
DATE ?=
WS_NAME ?=
WS ?=

.DEFAULT_GOAL := help
.PHONY: help doctor tools tag check check-data validate project workspace seed detect install install-noseed check scan lookup ready units review store cost diagrams publish verify status list test

help: ## Show this help
	@echo "agent-audit-kit $$(cat $(KIT)/VERSION)"
	@echo
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-15s %s\n", $$1, $$2}'
	@echo
	@echo "Typical run:"
	@echo "  make doctor && make tools && make tag"
	@echo "  make project NAME=my-app            # once per system; fill in the six-line Intake in project.md"
	@echo "  make workspace NAME=my-app SOURCE=<git url or path> REF=<commit> MODE=eval"
	@echo "  make seed WS=<workspace>                 # eval only: plants issues, writes the answer key"
	@echo "  make ready WS=<workspace>                # install + data check + scans"
	@echo "  cd <workspace> && claude                 # then: /audit   (resume: /audit resume)"
	@echo "  make diagrams publish verify WS=<workspace>"

doctor: ## Check tools, drawio-skill pin and kit tag
	@$(K) doctor

tools: ## Install what doctor reports missing (preview: bin/kit tools --dry-run)
	@$(K) tools

tag: ## Tag this kit version (skips if already tagged)
	@$(K) tag

project: ## NAME=<name>: create ~/audit-projects/<name> (never overwrites)
	@$(K) project $(NAME)

workspace: ## NAME= SOURCE= REF= [MODE=eval|real] [DATE=] [WS_NAME=]: create a workspace (skips if it exists)
	@$(K) workspace $(NAME) --source "$(SOURCE)" --ref "$(REF)" --mode $(MODE) $(if $(DATE),--date $(DATE)) $(if $(WS_NAME),--name $(WS_NAME))

seed: ## WS=: eval only, plant seeded issues; answer key goes to the project's keys/
	@$(K) seed "$(WS)"

detect: ## WS=: profiles, exclusions and facts from the files (no AI)
	@$(K) detect "$(WS)"

install: ## WS=: install or refresh the kit in a workspace
	@$(K) install "$(WS)"

install-noseed: ## WS=: install an eval workspace without seeded issues
	@$(K) install "$(WS)" --no-seed

validate: ## WS=: check models.yaml and the intake (pre-flight needs a pass)
	@$(K) validate "$(WS)"

check-data: ## WS=: data check (credentials, dumps, exports) in tree and history
	@$(K) check "$(WS)"

scan: ## WS=: run installed scanners (existing outputs kept; use bin/kit scan WS --force to redo)
	@$(K) scan "$(WS)"

lookup: ## WS=: npm deprecated, GitHub archived, Node.js end of life (only if .audit/policy.yaml allows)
	@$(K) lookup "$(WS)"

ready: ## WS=: install + detect + data check + scans + lookups + checkpoint
	@$(K) ready "$(WS)"

units: ## WS=: list the file review's units and write their briefs (no AI)
	@$(K) units "$(WS)"

review: ## WS=: run the file review, one claude -p pass per unit (ADR 0007)
	@$(K) review "$(WS)"

store: ## WS=: rebuild .audit/findings.duckdb from the records, traces and passes
	@$(K) store "$(WS)"

cost: ## WS=: turns, tokens, cost and time per stage and model
	@$(K) cost "$(WS)"

diagrams: ## WS=: build Diagram IR with the pinned drawio-skill
	@$(K) diagrams "$(WS)"

publish: ## WS=: Word, PowerPoint and PDF from the Markdown outputs
	@$(K) publish "$(WS)"

verify: ## WS=: automated output checks
	@$(K) verify "$(WS)"

status: ## WS=: workspace details, run state, active locks
	@$(K) status "$(WS)"

list: ## List workspaces
	@$(K) list

test: ## Run the kit's tests (pytest, including the bin/kit end-to-end test)
	@cd $(KIT) && uv run --frozen pytest

check: ## Run every quality gate from the lock (python-standards canonical commands)
	@cd $(KIT) && uv sync --frozen --quiet
	@cd $(KIT) && uv run --frozen ruff check .
	@cd $(KIT) && uv run --frozen ruff format --check .
	@cd $(KIT) && uv run --frozen mypy src tests
	@cd $(KIT) && uv run --frozen bandit -q -c pyproject.toml -r src
	@cd $(KIT) && uv run --frozen semgrep scan --config .semgrep.yml --metrics off --error --quiet src
	@cd $(KIT) && uv run --frozen pytest --cov --cov-branch
	@cd $(KIT) && f="$$(mktemp)" && uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements.txt --output-file "$$f" >/dev/null && uv run --frozen pip-audit --strict --no-deps --requirement "$$f"; rc=$$?; rm -f "$$f"; exit $$rc

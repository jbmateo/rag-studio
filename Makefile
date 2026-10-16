# Dev runner. uvicorn uses the app factory (--factory app.main:get_app) so importing
# app.main never creates storage/app.db or reads .env; only starting the server does.
BACKEND := backend
PY := $(BACKEND)/.venv/bin

.PHONY: setup dev test experiments

setup:
	cd $(BACKEND) && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	@if [ -d frontend ]; then npm --prefix frontend install; fi

dev:
	@trap 'kill 0' INT TERM; \
	(cd $(BACKEND) && .venv/bin/uvicorn app.main:get_app --factory --reload --port 8000) & \
	if [ -d frontend ]; then npm --prefix frontend run dev & fi; \
	wait

test:
	cd $(BACKEND) && .venv/bin/pytest -q
	cd frontend && npx tsc --noEmit && npm run lint && npx playwright test

experiments:
	@echo "Added in Task 15"; exit 1

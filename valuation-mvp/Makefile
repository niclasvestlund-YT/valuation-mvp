.PHONY: setup dev build deploy

setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && bun install
	@if [ ! -f backend/.env ]; then cp backend/.env.example backend/.env && echo "Created backend/.env — fill in your API keys"; else echo "backend/.env already exists"; fi

dev:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

build:
	cd frontend && bun run build
	rm -rf backend/static
	cp -r frontend/dist backend/static
	@echo "Frontend built and copied to backend/static"

deploy:
	$(MAKE) build
	railway up --service valuation-mvp

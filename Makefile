.PHONY: setup dev deploy context db db-stop

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example — fill in your API keys"; else echo ".env already exists, skipping"; fi

dev:
	.venv/bin/uvicorn backend.app.main:app --reload

deploy:
	@echo "=== Changes on dev not yet in main ==="
	@git log main..HEAD --oneline
	@echo ""
	@git diff --stat main..HEAD
	@echo ""
	@read -p "Deploy to production? (y/n) " confirm && [ "$$confirm" = "y" ] \
		&& git checkout main \
		&& git merge dev \
		&& git push \
		&& git checkout dev \
		&& echo "Deployed and back on dev" \
		|| echo "Cancelled"

db:
	docker run --name valuation-db -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=valuation -p 5432:5432 -d postgres:16
	@echo "PostgreSQL running on localhost:5432"
	@echo "DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/valuation"

db-stop:
	docker stop valuation-db && docker rm valuation-db

context:
	@echo "CONTEXT.md status:"
	@wc -l CONTEXT.md
	@echo ""
	@git diff --stat CONTEXT.md 2>/dev/null || echo "Not yet committed"

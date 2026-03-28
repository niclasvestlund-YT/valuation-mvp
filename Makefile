.PHONY: setup dev stage-ready stage deploy context db db-stop

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example — fill in your API keys"; else echo ".env already exists, skipping"; fi

dev:
	.venv/bin/uvicorn backend.app.main:app --reload

stage-ready:
	@sh scripts/stage_ready_check.sh

stage:
	@if [ -n "$$(git status --porcelain)" ]; then echo "ERROR: worktree is dirty — commit or stash first" && exit 1; fi
	@git rev-parse --verify develop >/dev/null 2>&1 || (echo "ERROR: branch 'develop' not found" && exit 1)
	@git rev-parse --verify staging >/dev/null 2>&1 || (echo "ERROR: branch 'staging' not found" && exit 1)
	@echo "=== Changes on develop not yet in staging ==="
	@git log staging..develop --oneline
	@echo ""
	@git diff --stat staging..develop
	@echo ""
	@echo "Running stage-ready checks first..."
	@$(MAKE) stage-ready || (echo "Stage-ready checks failed — aborting stage deploy" && exit 1)
	@echo ""
	@ORIG_BRANCH=$$(git symbolic-ref --short HEAD) && \
		read -p "Deploy to staging? (y/n) " confirm && [ "$$confirm" = "y" ] \
		&& git checkout staging \
		&& git merge --no-edit develop \
		&& git push \
		&& git checkout "$$ORIG_BRANCH" \
		&& echo "Merged develop → staging and back on $$ORIG_BRANCH" \
		|| (git checkout "$$ORIG_BRANCH" 2>/dev/null; echo "Cancelled or failed — back on $$ORIG_BRANCH")

deploy:
	@if [ -n "$$(git status --porcelain)" ]; then echo "ERROR: worktree is dirty — commit or stash first" && exit 1; fi
	@git rev-parse --verify staging >/dev/null 2>&1 || (echo "ERROR: branch 'staging' not found" && exit 1)
	@git rev-parse --verify main >/dev/null 2>&1 || (echo "ERROR: branch 'main' not found" && exit 1)
	@echo "=== Changes on staging not yet in main ==="
	@git log main..staging --oneline
	@echo ""
	@git diff --stat main..staging
	@echo ""
	@ORIG_BRANCH=$$(git symbolic-ref --short HEAD) && \
		read -p "Deploy staging → production? (y/n) " confirm && [ "$$confirm" = "y" ] \
		&& git checkout main \
		&& git merge --no-edit staging \
		&& git push \
		&& git checkout "$$ORIG_BRANCH" \
		&& echo "Merged staging → main (production) and back on $$ORIG_BRANCH" \
		|| (git checkout "$$ORIG_BRANCH" 2>/dev/null; echo "Cancelled or failed — back on $$ORIG_BRANCH")

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

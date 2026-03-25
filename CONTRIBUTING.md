# Contributing — valuation-mvp

## Branch workflow

```
develop  →  staging  →  main
(daily)     (test)      (production)
```

### develop
- All daily work happens here.
- Claude Code pushes to this branch.
- Feature branches (optional): branch off `develop`, merge back via PR.

### staging
- Pre-production testing.
- Merge `develop → staging` when a set of changes is ready to verify.
- Deploy to staging environment for QA.

### main
- Production branch. Never commit directly.
- Merge `staging → main` is a manual owner decision only.
- Protected: requires PR + approval, no direct pushes.

## Commit format

```
type: short description
```

| Type       | Use for                              |
|------------|--------------------------------------|
| feat       | New feature or capability            |
| fix        | Bug fix                              |
| refactor   | Code restructuring, no behavior change |
| docs       | Documentation only                   |
| infra      | CI/CD, deployment, tooling, config   |
| security   | Security fixes or hardening          |

## Rules

1. Never commit `.env` or secrets.
2. Run tests before pushing: `python -m pytest tests/`
3. Update `CONTEXT.md` after every task (per CLAUDE.md rules).
4. Keep commits small and focused — one concern per commit.

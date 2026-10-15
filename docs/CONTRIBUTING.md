# CONTRIBUTING — Autonomous AI Video Recap Platform

Thanks for helping build a free AI recap platform for everyone. This guide keeps contributions safe, consistent, and reviewable.

## Ground rules

1. **Secrets live in env only — never in code, never in a PR.** No API keys, tokens, passwords, private keys, or connection strings in source, tests, docs, or commit messages. CI runs `scripts/secret_scan.py` and fails the build on any hit.
2. **FREE only.** Do not add payment, billing, paywall, or premium-tier code. PRs introducing any will be closed.
3. **Burmese-first.** User-facing strings default to Burmese (`my`); English via the i18n toggle. Don't ship English-only UI.
4. **Contract-first.** The API surface is defined in `docs/API_DOCUMENTATION.md`. Changing/adding an endpoint requires updating the doc in the same PR and keeping `scripts/contract_check.py` green.

## Development setup

```bash
git clone <repo-url> && cd AI-VIDEO-RECAP-PLATFORM
cp .env.example .env   # fill with your own dev values (never commit)

# backend
cd backend && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload          # > NOTE (unverified): confirm entrypoint name

# frontend
cd frontend && npm install && npm run dev

# or everything at once:
docker compose up --build
```

## Code style

| Area | Style |
|------|-------|
| Python (backend) | `black` + `ruff`; type hints on public functions; docstrings on agents |
| TypeScript (frontend) | `prettier` + `eslint` (next config); no `any` in new code |
| Commits | Conventional: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:` |
| Migrations | One `supabase/migrations/*.sql` file per change, prefixed `NNN_description.sql`, must be re-runnable in order |

## Pull request process

1. Fork → feature branch (`feat/whisper-diarization`, `fix/sse-reconnect`…).
2. Keep PRs small and single-purpose. Include: what changed, how you tested, screenshots for UI changes.
3. `python3 scripts/secret_scan.py` and `python3 scripts/contract_check.py` must pass — CI enforces both.
4. One approving review required. The reviewer checks: no secrets, no payment code, i18n strings present, API doc updated if endpoints changed.
5. Squash-merge with a conventional-commit message.

## Adding things the plugin way

- New AI provider / agent / exporter → follow `docs/PLUGIN_GUIDE.md` (implement the interface, register in one place, add tests + docs). Don't fork core files when a plugin hook exists.

## Reporting security issues

Don't open a public issue. See `docs/SECURITY.md` for the current reporting process (no private email contact is published yet). We aim to acknowledge within 72 hours.

## Good first issues

Look for issues labeled `good-first-issue`: usually i18n strings, FAQ/docs updates, small frontend components, or new tests for an agent.

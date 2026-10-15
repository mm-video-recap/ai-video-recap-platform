# STEP 7 — GitHub Public Repository Setup Plan

**Project:** AI Video Recap Platform
**Project root:** `~/workspace/AI-VIDEO-RECAP-PLATFORM`
**Plan date:** 2026-10-15 (Asia/Yangon)
**Plan type:** READ-ONLY planning document. **No action has been taken.** No remote configured, no repository created, no push/pull/fetch, no commit/amend/reset/rebase, no source/report/PDF modification, no deployment, no migration.

**Confirmed inputs:**
- Local branch: `main`
- Local first commit: `99556eab3fd471357aa7c2d8e0ee9052d07f47c0` (151 files, 19,155 insertions)
- Commit author: `myan recap bro <cbuserlay@gmail.com>`
- Intended visibility: **Public**
- GitHub account: `mm-video-recap` (signed-in session confirmed in browser)

---

## 1. Current Git state (verified read-only)

| Item | State |
|---|---|
| Branch | `main` |
| Commits | 1 (root commit `99556ea`) |
| Working tree | Clean (empty `git status`) |
| Remotes | None (`git remote -v` empty) |
| Files in commit | 151 (per `git show --stat`: 19,155 insertions, 0 deletions) |

---

## 2. Committed-content security review

Method: `git grep` against the committed tree (`HEAD`) for 12 secret classes, plus targeted shape-only / type-only inspection of n8n credential blocks, migration lines, and email-pattern lines. **No secret values were printed at any point.**

### 2.1 Result: NO real secrets, credentials, or private configuration in the commit

| Class | Result |
|---|---|
| Private-key blocks (`-----BEGIN … PRIVATE KEY-----`) | None |
| AWS keys (`AKIA…`) | None |
| Slack tokens (`xox…`) | None |
| GitHub PATs (`ghp_…` / `github_pat_…`) | None |
| OpenRouter keys (`sk-or-v1-…`) | None |
| Generic `sk-…` keys | None |
| Real JWTs | None (only placeholder-shaped strings, §2.2) |
| Hardcoded passwords | None (only false positives, §2.2) |
| `api_key` / `access_token` / `secret_key` assignments with real values | None |

### 2.2 Benign findings (carried forward from the STEP 5 audit — all triaged, not leaks)

- **`.env.example` key-shaped placeholders** (JWT-shaped lines 44/46/169; `AIza…` lines 71/75/76/77; `gsk_…` lines 81/84/85; `hf_…` line 97; connection-string lines 39/61/62/63): all contain placeholder hints (verified by aggregate placeholder-marker check in STEP 4). They mimic key formats and will trip naive scanners — a process note, not a leak.
- **`TEST_RESULTS.md:274`**: masked `gsk_***…` documentation example, not a key.
- **Password-pattern false positives**: `frontend/app/login/page.tsx:153` (`autoComplete` attribute), `frontend/locales/en.json:93`, `frontend/locales/my.json:93` (i18n labels). One additional match in `STEP5_PRE_COMMIT_AUDIT_REPORT.md:56` is the audit's own description of the false-positive class.
- **`Bearer …` hits** (`backend/api/deps.py:43`, `backend/config.py:41`, `backend/main.py:6`, tests, `docs/SECURITY.md:9`, `.env.example:30`): `Authorization: Bearer …` format documentation/comments, not tokens.
- **Connection strings** (CI lines 47–50, `backend/config.py:83-85`, `docker-compose.yml`, `conftest.py:21-23`, reports): localhost / env-var defaults / test fixtures / doc examples.
- **Migration `001_init.sql`**: schema DDL + comments only. "Key" hits are `PRIMARY KEY` column definitions and comments about `service_role`/`anon` key behavior. **No key values.**
- **n8n workflows**: 7 `credentials` blocks across 3 workflows — type-only inspection confirms every block is `{id: null, name: <display label>}`. These are unbound credential **references**, not credential material. No passwords, tokens, or IDs.
- **Email-pattern lines in files (11 hits)**: all placeholders / examples / test fixtures / UI strings — `deps.py:34` (service identity), `conftest.py:24,65` (test fixtures), `docs/API_DOCUMENTATION.md:49,152` (example JSON), `frontend/locales/*.json` (`emailPlaceholder`, `securityEmail` UI strings), `.env.example:39` (placeholder DSN). **Exception / pre-launch TODO:** `docs/SECURITY.md:47` and the locale `securityEmail` strings hold a placeholder security-contact address explicitly marked "replace with the real address before launch" — a real contact must be set (or the line removed) before launch; see §5.
- **Personal data**: the strings `cbuserlay` and `myan recap` appear **nowhere in any committed file** — only in the commit's author metadata (§6).
- **Internal paths**: 3 hits in reports (`PROJECT_COMPLETION_REPORT.md:123,577`, `TEST_RESULTS.md:14`) reference `~/workspace/…` paths. Low risk, informational — they reveal a local directory layout, not credentials.
- **Supabase project-ref mentions** (12 hits: `.env.example`, CI, guides, reports, migration comment): the project ref / URL is an **identifier, not a secret** — the URL alone grants nothing. The anon key is not in the repo; the service-role key is never in the repo. Publishing the ref identifies the live Supabase project (Low risk, acceptable). Protection comes from RLS + key secrecy, not from hiding the ref.

### 2.3 Scan limitations (stated, not hidden)

- `backend/venv/`, `frontend/node_modules/`, `frontend/.next/` contents were **not** content-scanned (generated dirs). They are gitignored and **not** in the commit, so they cannot leak via this push.
- The PDF was not byte-scanned (binary); its text was extracted and its claims reviewed (§4).
- Files that fail UTF-8 decoding are silently skipped by `scripts/secret_scan.py`.
- The repo scanner's placeholder filter means placeholder-shaped strings are intentionally not flagged — the independent pattern scan above is the backstop, and it agrees.

---

## 3. Outdated Git claims to fix (DO NOT fix in this step)

`PROJECT_COMPLETION_REPORT.md` and the PDF were written before `git init`. They contain claims that are now false. **Fix in a follow-up commit before pushing** (see §8), so the public history does not start with a false claim.

| Location | Current (outdated) claim | Correct statement |
|---|---|---|
| `PROJECT_COMPLETION_REPORT.md` line 53 | "`.git` မရှိပါ — this repo is not a git repo yet" | `.git` exists; branch `main`; first commit `99556ea` created 2026-10-15. GitHub push still pending. |
| `PROJECT_COMPLETION_REPORT.md` line 473 / B17 row | "`.git` မရှိပါ — deployment needs a GitHub repo" | `git init` DONE. B17 now = "GitHub repo creation + push pending". |
| `AI_VIDEO_RECAP_FINAL_PROJECT_REPORT.pdf` (extracted-text lines ~61, ~318, ~1225) | Same "`.git` မရှိပါ" claim | Same correction; **regenerate the PDF** after fixing the markdown. |
| `STEP5_PRE_COMMIT_AUDIT_REPORT.md` | "Commits: none yet" | Was accurate at audit time (point-in-time record). **Do NOT rewrite it** — it remains valid audit evidence of the pre-commit state. |

Other report claims remain accurate and need no change: verdict **NOT READY**, Docker build / real AI recap / dependency audit honestly marked NOT TESTED / NOT RUN, Supabase B2 DONE (per prior session's browser verification; not re-verifiable locally), `next.config.mjs` still `{}`.

---

## 4. Public-repo suitability review

| Item | State | Public-repo verdict |
|---|---|---|
| Root `README.md` | **MISSING** (only `docs/README.md` + `frontend/README.md` exist; GitHub shows the root README) | **Gap — create one** before push (§7). Proposed outline in §7; content needs owner approval. |
| `LICENSE` / `LICENSE.md` | **MISSING** | **Decision required — do NOT choose for the user** (§7). Without a license, public visibility does **not** grant reuse rights (code stays "all rights reserved" by default). |
| Root `SECURITY.md` | Missing at root, but **`docs/SECURITY.md` exists** (GitHub recognizes `docs/SECURITY.md`) | Acceptable as-is for GitHub's security-policy detection. **But:** it contains the placeholder security contact (§2.2) — set a real contact or remove the line before push. |
| `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` | Missing at root; `docs/CONTRIBUTING.md` exists | Optional. Not blockers for a solo project. |
| `.gitignore` | 104 lines, hardened (STEP 4: `.npmrc`, `docker-compose.override.yml`, `*.crt`, `*.cer`, `.vercel/`, `.netlify/`, `.cloudflare/`, `*.tar.gz`, `*.zip` + prior rules). Verified active via `check-ignore`. | ✅ Ready |
| `.env.example` (root + frontend) | Placeholders only, verified (§2.2). Frontend copy has empty Supabase values + `localhost` API URL. | ✅ Safe to publish |
| CI (`.github/workflows/ci.yml`, 145 lines) | Zero `${{ secrets.* }}` references (line 144 is prose in an echo: "cloud accounts and secrets"). Runs backend tests, frontend build, secret scan, compose validation; manual-only deploy placeholder exits 0. **Does not deploy.** | ✅ Safe to publish; CI will run on the public repo |
| n8n workflows (3 JSONs) | Credential blocks are null-ID references only (§2.2). No credential material. | ✅ Safe to publish |
| Supabase migration (`001_init.sql`, 277 lines) | Schema + RLS + comments only. **Non-idempotent; already applied once live.** | ✅ Safe to publish **with a README warning: never re-run** (already applied; re-running will fail / could damage the live DB) |
| `PROJECT_COMPLETION_REPORT.md` (679 lines) | Contains workspace paths + Supabase ref + honest NOT READY verdict. | ✅ Publishable after §3 fixes |
| `AI_VIDEO_RECAP_FINAL_PROJECT_REPORT.pdf` (295,483 bytes binary) | Binary blob; will live in git history forever; contains the outdated git claim. | ⚠️ Regenerate after §3 fixes, then publish |
| `DEPLOYMENT_GUIDE.md` (232 lines) | Setup instructions; tells operators to put secrets in hosting Secrets, never in chat/code. Contains Supabase ref (identifier, not secret). | ✅ Publishable |
| `STEP5_PRE_COMMIT_AUDIT_REPORT.md` | Point-in-time audit record; states "no commits" (true then). | ✅ Publishable as-is (do not rewrite) |
| `TEST_RESULTS.md` | Test evidence; masked examples only. | ✅ Publishable |

---

## 5. Commit author email — exposure risk and the hash-change rule

### 5.1 The risk
The commit's author line is `myan recap bro <cbuserlay@gmail.com>`. It is **part of the commit object**. Once pushed to a public repo, the email becomes publicly visible in:
- GitHub's commit page / history view,
- `git log` for anyone who clones the repo,
- GitHub's API responses for the commit.

It also links the commits to the `mm-video-recap` GitHub profile (the email matches the account's primary email). Practical risk: **Low–Moderate** — mainly spam harvesting and account linkability. The address is already the account's GitHub notification address (created via Google OAuth), so this is not exposing a previously private mailbox — but the owner should decide knowingly.

### 5.2 The hash-change rule
A git commit hash covers **everything** in the commit: tree, message, timestamps, **and the author name/email**. Changing the author email therefore requires **rewriting the commit** (amend / rebase), which produces a **new, different hash** — the current `99556ea…` would cease to be the commit, and every reference to it (STEP 5 report, this plan, prior chat messages) would point at the old, superseded hash.

**Crucial timing fact:** nothing has been pushed yet, there are no collaborators, and no remote exists — so rewriting now is **safe and cheap**. After the first push, rewriting would require a force-push and is strongly discouraged.

### 5.3 Options (decision required — NO action taken)

| Option | What happens | Consequence |
|---|---|---|
| **A. Keep `cbuserlay@gmail.com`** | No rewrite. Push as-is. | Simplest. Email is publicly visible in history (see §5.1). |
| **B. Rewrite with GitHub noreply address** | Amend the single root commit to author `<id>+mm-video-recap@users.noreply.github.com` (the exact address is shown in GitHub → Settings → Emails → "Keep my email address private"). | Commit hash **changes**; must re-verify `git log` / `git status` after. Real email stays hidden from history. Requires the owner to supply/confirm the exact noreply address (or approve reading it from Settings). |
| **C. Keep commit + harden future commits only** | Enable GitHub's "Keep my email address private" + "Block command line pushes that expose my email" for the account. | Protects **future** commits only. Does **not** hide the email already in this commit. |

---

## 6. Recommended repository setup (decisions needed — plan only)

| Setting | Recommendation | Status |
|---|---|---|
| Owner | `mm-video-recap` (confirmed signed-in account) | Confirmed |
| Repository name | **`ai-video-recap-platform`** (matches project directory + goal; clearly distinct from the existing `mm-video-recap/mm-video-recap` Streamlit repo — the platform must **never** be pushed into that repo) | Recommended; needs owner confirmation. Alternative: `ai-video-recap` (shorter). |
| Description | "Free, autonomous AI video recap platform — FastAPI backend (8 AI agents, Celery queue), Next.js frontend, Supabase, Docker + CI. Upload a video, get a Myanmar/English recap." | Proposed; owner may edit |
| Default branch | `main` (already the local branch) | Confirmed |
| Visibility | **Public** | Confirmed by owner |
| Topics (optional) | `ai`, `video-recap`, `fastapi`, `nextjs`, `celery`, `supabase`, `myanmar`, `burmese` | Optional; owner decides |
| README | Create root `README.md` before push (outline below) | Needs owner approval of content |
| LICENSE | **Owner must choose** — see options table | **DECISION REQUIRED** |
| Security settings | Verify after creation: Secret scanning + Push protection **ON** (free for public repos, on by default — verify, don't assume); Dependabot alerts + security updates **ON**; Private vulnerability reporting **ON** | Verify post-creation |
| Branch protection on `main` | **Recommended: none initially** (solo dev; avoids blocking the first push). Revisit after the first successful CI run — then consider requiring status checks. | Recommended; owner decides |
| `.gitignore` / CI / workflows | Use the repo's own files; **do NOT** let GitHub auto-add a README / LICENSE / `.gitignore` at creation (would conflict with the local repo) | Must be explicit at creation |

### 6.1 LICENSE options (owner chooses — no default imposed)

| License | Effect |
|---|---|
| MIT | Permissive — anyone can use / modify / sell with attribution. Most common for this kind of project. |
| Apache-2.0 | Permissive like MIT + explicit patent grant. |
| BSD-3-Clause | Permissive like MIT + no-endorsement clause. |
| GPL-3.0 | Copyleft — derivatives must also be GPL-3.0. |
| No license (proprietary) | Public visibility grants **no** reuse rights; code is "all rights reserved" by default. |

Note: the license covers code. The Burmese PDF report / docs are documentation; if the owner wants them under a different license (e.g. CC BY), say so — otherwise the repo license is assumed to cover the whole repo.

### 6.2 Proposed root README outline (content needs owner approval)

1. Title + one-line description + **NOT READY / not deployed** banner (the verdict is NOT READY — the README must say so, so visitors don't mistake the repo for a live service).
2. What it is (8 agents, queue, provider manager, Next.js frontend, Supabase, Docker + CI).
3. Project status checklist (what's done / what's not: deployment, real AI recap, Docker build, dependency audit).
4. Quickstart for local development (env setup via `.env.example`, `docker compose up`, tests).
5. **Migration warning: `001_init.sql` is non-idempotent and already applied to the live Supabase project — never re-run it.**
6. Security note (secrets via env / hosting Secrets only, never in code; link to `docs/SECURITY.md`).
7. License section (filled in once the owner chooses).

---

## 7. Execution sequence (AFTER owner approval — NOT executed now)

1. **Owner decisions:** license choice; README content approval; security-contact fix (real address or remove line); author-email option (A / B / C from §5.3); repo name confirmation.
2. **If email option B:** rewrite the single root commit with the noreply author; re-verify `git log -1`, `git status`, and the new hash; note the old hash as superseded.
3. **Second commit (local):** fix outdated git claims in `PROJECT_COMPLETION_REPORT.md`, regenerate the PDF, add root `README.md` + `LICENSE` (+ security-contact fix). Verify `git status` / `git log` after.
4. **Create the GitHub repo via browser** (signed-in `mm-video-recap`): Public, default branch `main`, **do NOT** tick "Add a README / LICENSE / .gitignore" (local repo already has them — auto-adding would conflict).
5. **Add remote** (only after explicit approval of the exact URL): `git remote add origin https://github.com/mm-video-recap/ai-video-recap-platform.git`, then verify `git remote -v`.
6. **Push:** `git push -u origin main`. Verify on GitHub: commit visible, file list matches, CI workflow runs, secret-scanning alerts = none.
7. **Post-push verification:** confirm security settings (§6), confirm the README renders, confirm no secret-scanning alert.
8. **Never re-run** `supabase/migrations/001_init.sql`.

---

## 8. Risks

| Risk | Likelihood / impact | Mitigation in this plan |
|---|---|---|
| Author email publicly visible in history | Certain if Option A / Medium impact | Owner decision (§5.3); Options B/C available before push |
| Placeholder-shaped strings in `.env.example` confuse a future scanner / maintainer | Medium / Low | Documented as placeholders (§2.2); repo scanner has a placeholder filter |
| A third party re-runs the migration against the live DB | Low / **High** | README warning (§6.2); migration file header already warns |
| Public repo mistaken for a live/production service | Medium / Medium | NOT READY banner in README (§6.2); verdict stays NOT READY |
| PDF binary in history forever (with outdated claim if not regenerated) | Certain if skipped / Low | Regenerate after report fix, before push (§7 step 3) |
| GitHub auto-added README/LICENSE/.gitignore conflicts with local repo | Low / Medium | Explicit "do NOT auto-add" instruction (§7 step 4) |
| Reports expose workspace paths / Supabase project ref | Certain / Low | Identifiers only, no secrets (§2.2); accepted |
| Secret-scanning alert on placeholder strings after push | Low / Low | Placeholders documented; dismiss as false positive only after verifying the exact alert matches a known placeholder |

---

## 9. Confirmation

- ✅ No remote added, set, or removed.
- ✅ No GitHub repository created.
- ✅ No push, pull, or fetch.
- ✅ No commit, amend, reset, rebase, or history rewrite.
- ✅ No source code, report, or PDF modified.
- ✅ No deployment, migration, destructive operation, or spending.
- ⏸️ **Plan only. Stopped. Awaiting owner approval for the next step.**

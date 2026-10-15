# STEP 8 — Public Push Preparation Plan (Local Only)

**Project:** AI Video Recap Platform
**Project root:** `~/workspace/AI-VIDEO-RECAP-PLATFORM`
**Plan date:** 2026-10-15 (Asia/Yangon)
**Plan type:** Preparation plan ONLY. **No action has been taken.** This step creates only this plan file.

**Starting state (verified read-only):**
- Branch: `main`, 1 commit: `99556eab3fd471357aa7c2d8e0ee9052d07f47c0` (151 files)
- Author: `myan recap bro <cbuserlay@gmail.com>`
- Remote: none. Push: **not done, and NOT part of this plan.**
- Untracked: `STEP7_GITHUB_PUBLIC_SETUP_PLAN.md` (from STEP 7)

**Owner decisions (binding for this plan):**
- **LICENSE: No license.** Do NOT create a `LICENSE` file. The README must state clearly that there is no license and that public visibility alone grants no reuse permission.
- **Author email:** Switch to the GitHub noreply address **before** push — but the exact address is **NOT yet confirmed**. The owner must confirm the exact address from GitHub → Settings → Emails. **Do NOT guess the address. Do NOT modify account settings.**
- **README outline: approved.** Must include: NOT READY banner, done / not-done status, local setup, security note, migration warning, no-license statement.
- **Security contact: REMOVE the placeholder.** Inventory all placeholder-contact locations (§2c). **Do NOT add a fake / invented contact.**
- **Outdated Git claims in project reports:** fix them. **Regenerate the PDF only after** the markdown report is fixed. **STEP 5 audit stays untouched** as a historical snapshot.
- **Migration:** never re-run `supabase/migrations/001_init.sql`. Migration warning goes in the README.

**Strict limits for the execution phase (when approved):**
- Only this plan file may be created in THIS step. During execution: no files may be created/modified/deleted except the ones listed in §2–§4.
- No `git add -A` (blind staging forbidden). Stage only the explicit reviewed list (§4).
- No remote add/set/remove. No GitHub repo creation. No push/pull/fetch.
- No GitHub Settings changes, no email changes outside the local commit rewrite (§1).
- No deployment. No migration run. No secrets in any report or terminal output.

---

## Approval checkpoints

| Checkpoint | When | Owner confirms |
|---|---|---|
| **CP-1** | Before ANY action (before §1) | Exact noreply address (copied from GitHub Settings → Emails); README content; security-contact removal approach; second-commit message; that push is OUT of scope |
| **CP-2** | After §1 (author rewrite) | New commit hash; author + committer both show the noreply address |
| **CP-3** | After §2 + §3 (content fixes + PDF) | Full `git diff` review; regenerated PDF check (page count, p.1 shaping, updated git claim) |
| **CP-4** | After §4 (second commit) | Final `git log` (2 commits), clean `git status`, secret scan clean. **Push still needs a SEPARATE approval** |

---

## Phase 1 — Author email rewrite (FIRST — before any new commit)

**Purpose:** Replace the commit author email with the GitHub noreply address so the real email never appears in public history. Must happen **before** any push and **before** the second commit, so the second commit builds on the rewritten root.

**Order:** This is step 1 of execution. Do not create the second commit first — the second commit must sit on top of the rewritten root commit.

**Affected files:** None (working tree untouched). Affected object: the single root commit (metadata only — tree unchanged).

**Steps:**
1. Verify clean starting state:
   - `git status --short` → empty (except untracked STEP 7 plan file, which is expected)
   - `git log -1 --format='%H %an <%ae>'` → `99556ea… myan recap bro <cbuserlay@gmail.com>`
   - Record the old tree hash: `git rev-parse HEAD^{tree}` (save it for step 4 comparison)
2. Owner supplies the **exact** noreply address from GitHub → Settings → Emails ("Keep my email address private" section). The address has the GitHub noreply form (`<id>+mm-video-recap@users.noreply.github.com`) — **copy it exactly; do NOT construct or guess the numeric ID.**
3. Update **local repo config only** (never `--global`):
   - `git config user.email "<exact-noreply-address>"`
   - Leave `user.name` as `myan recap bro`.
4. Rewrite the single root commit (metadata only):
   - `git commit --amend --reset-author --no-edit`
   - (`--reset-author` makes BOTH author and committer use the current local config, so no trace of the real email remains in either field.)
5. Verify:
   - `git log -1 --format='commit %H%nAuthor: %an <%ae>%nCommitter: %cn <%ce>'` → new hash, author AND committer both show the noreply address, message unchanged.
   - `git rev-parse HEAD^{tree}` → **must equal the tree hash from step 1** (proves content is byte-identical; only metadata changed).
   - `git show --stat --oneline HEAD` → still 151 files, same insertions.
   - `git status --short` → clean (except untracked STEP 7 plan file).
   - `git remote -v` → still empty.
6. **STOP for CP-2.** Owner confirms the new hash.

**Risks:**
- The old hash `99556ea…` becomes superseded. References to it in STEP 5 / STEP 7 / STEP 8 docs remain as **historical records — do NOT edit them** to the new hash (that would falsify the audit trail). The new hash is the live one from here on.
- If the noreply address is mistyped, the commit will carry a wrong author. Mitigation: CP-1 (owner confirms exact address) + step 5 verification before proceeding.
- **Never** run this rewrite after a push. If a push ever happens first, the email is public and rewriting would require a force-push — forbidden without a separate explicit decision.
- **Branch:** If the owner declines the noreply switch (keeps Option A, real email), **skip this entire phase** and proceed to Phase 2 on top of `99556ea`.

---

## Phase 2 — Content fixes (working tree, uncommitted)

### 2a. Outdated Git claims in `PROJECT_COMPLETION_REPORT.md`

| Location | Current (outdated) | Replacement |
|---|---|---|
| Line 53 | "`.git` **မရှိပါ** — ဤ repo သည် git repo မဟုတ်သေးပါ" | `.git` ရှိပြီး၊ branch `main`၊ first commit ဖန်တီးပြီး။ GitHub push မလုပ်ရသေးပါ။ |
| Line 473 (B17 row) | "`.git` မရှိပါ — deployment သည် GitHub repo ကို လိုသည်" | `git init` ပြီးစီးပြီး။ B17 ကျန် = GitHub repo ဖန်တီးခြင်း + push။ |
| Line 511 (B17 task row) | "Git init + GitHub push \| P0" (status implies not started) | Status update: `git init` DONE (commit hash as of this phase); GitHub push PENDING. |

**Explicitly do NOT change:** line 557 ("B17 — GitHub repo ရှိပြီး") is a *requirement* for READY FOR STAGING, not a current-state claim — still accurate. Line 671 ("နောက်တစ်ဆင့် … B17 (GitHub) …") is a next-step statement — still accurate. Do not over-edit.

### 2b. Outdated Git claim in `DEPLOYMENT_GUIDE.md`

| Location | Current (outdated) | Replacement |
|---|---|---|
| Step 0 bullet (~line 46) | "Note: the working copy has no `.git` yet — the user creates the repo via browser takeover, then run `git init`…" | Working copy already has `.git` (branch `main`, local commit done). Remaining: create the GitHub repo (via browser, signed-in `mm-video-recap`) + push after separate approval. |

### 2c. Security-contact placeholder removal

**Rule:** Remove the placeholder. Do NOT add any invented contact. The replacement wording must not promise a private channel that does not exist yet.

| File | Location | Action |
|---|---|---|
| `docs/SECURITY.md` | Lines 45–49 ("Do not open a public issue. Email the security contact…" + placeholder line + "replace with the real address" note) | Remove the placeholder contact line and the "replace" note. Replace with: no private email contact is published yet; **do not post exploit details publicly**; vulnerability reports will be handled via GitHub **private vulnerability reporting** once the repo is public (to be enabled at repo creation — a follow-up step, not this phase). |
| `docs/CONTRIBUTING.md` | Lines 51–53 ("See `docs/SECURITY.md` for the private contact") | Reword: no private contact is published yet; see `docs/SECURITY.md` for the current reporting process. |
| `frontend/locales/en.json` | Lines 133–135 (`securityDesc`, `securityEmail: "security@example.com"`, `securityTitle`) | **Remove all three keys** (the whole security block is removed from the UI). |
| `frontend/locales/my.json` | Lines 133–135 (same three keys, Burmese) | **Remove all three keys.** |
| `frontend/app/contact/page.tsx` | Lines ~189–197 (security block: heading + description + `mailto:${t("contact.securityEmail")}` link + display) | **Remove the entire security block.** Keep the support / bug / feature forms (they post via the API, not email). |

**Keep (NOT contacts):**
- `frontend/locales/en.json:81` + `my.json:81` (`emailPlaceholder`) — a form input placeholder, not a contact. Leave unchanged.
- `docs/API_DOCUMENTATION.md:49,152` (example JSON emails) — API doc examples. **Verify** they use example-domain addresses (`example.com` / `example.org` style); if confirmed, leave unchanged. If any is a real-looking address, replace it with an example-domain address in this phase.

**Verification (after edits):**
- `grep -rn "securityEmail" frontend/ docs/` → **zero matches** (except this plan file, which is documentation).
- `grep -rn "securityTitle\|securityDesc" frontend/` → **zero matches**.
- `grep -rn "security@example.com" . --exclude-dir=node_modules --exclude-dir=venv --exclude-dir=.next` → **zero matches** in source (plan-file mentions excluded by review).
- `grep -rn "\.git.*မရှိ\|no .git" PROJECT_COMPLETION_REPORT.md DEPLOYMENT_GUIDE.md` → **zero matches** (historical mentions in STEP 5 / STEP 7 plan files are expected and must NOT be edited).

### 2d. Root `README.md` creation (NEW file)

Create `README.md` at the project root. Required sections (per approved outline — content needs CP-1 approval):

1. **Title + NOT READY banner** — "⛔ NOT READY — not deployed, not a live service." (The verdict is NOT READY; the README must say so so visitors don't mistake the repo for a live service.)
2. **What it is** — 8 AI agents, Celery queue, AI provider manager, Next.js frontend, FastAPI backend, Supabase, Docker + CI. Burmese-first UI.
3. **Status: done / not done** — done: code, tests (38 pytest per TEST_RESULTS.md), local E2E (stubbed highlight), Supabase setup (per report). Not done: deployment, real AI recap, Docker build, dependency audit, RLS cross-user test, Auth providers.
4. **Local setup** — copy `.env.example` → `.env` locally (never commit `.env`), `docker compose up`, run tests (`backend/venv/bin/python -m pytest backend/tests -q`, `cd frontend && npm run build`). Source from `DEPLOYMENT_GUIDE.md` + `docs/USER_GUIDE.md`; do not invent steps.
5. **Security note** — secrets via env vars / hosting Secrets only, never in code or chat; link to `docs/SECURITY.md`; no private security contact is published yet (see §2c).
6. **Migration warning (mandatory)** — `supabase/migrations/001_init.sql` is **non-idempotent and already applied once** to the live Supabase project. **Never re-run it.** Future schema changes need a new follow-up migration.
7. **License / no-license statement (mandatory)** — "This repository has **no license**. Public visibility alone does **not** grant permission to use, copy, modify, or distribute this code. All rights reserved unless the owner adds a license later."

**Verification:** every required section present (`grep` for headings / keywords); no secret values (secret scan, §2e); no claim of a live service.

### 2e. Verification of Phase 2 (before committing)

- `git status --short` → changed/new files must match the expected set exactly (see §4).
- `git diff` → read the **full** diff; confirm only intended changes.
- `python3 scripts/secret_scan.py` → exit 0, clean.
- Frontend (locales + contact page changed): `cd frontend && npx tsc --noEmit` (exit 0) + `npm run build` (exit 0). Build artifacts land in gitignored `.next/` — fine.
- Backend (docs-only change for backend): `backend/venv/bin/python -m pytest backend/tests -q` → expect 38 passed (re-confirms nothing broke; docs don't affect tests).
- `grep` checks from §2c + §2d.

---

## Phase 3 — PDF regeneration (AFTER the markdown report fix)

**Task:** Regenerate `AI_VIDEO_RECAP_FINAL_PROJECT_REPORT.pdf` from the updated `PROJECT_COMPLETION_REPORT.md`.

**Method (recorded pipeline — re-establish, do not improvise):** markdown → HTML with Noto Sans Myanmar font → WeasyPrint. **Chromium headless `--print-to-pdf` does NOT work in this sandbox — do not use it.** (The previous helper script was deleted after use; recreate the pipeline per this recorded method.)

**Verification:**
- Page count recorded (previously 31 pages; new count may differ — record the actual count).
- Burmese shaping check: render p.1 (+ one table page) via `pdftoppm` and visually confirm shaping.
- Extract text and confirm: updated git claim present ("`.git` ရှိပြီး" / "git init DONE" wording); **no** remaining "`.git` မရှိပါ" claim in the PDF text (historical mentions in other files are out of scope for this check).
- File size + timestamp recorded.

**Risk:** PDF tooling (WeasyPrint / fonts) may need re-installation in a fresh environment — if the pipeline cannot run, STOP and report; do not ship the stale PDF with the outdated claim.

---

## Phase 4 — Second commit (LOCAL ONLY)

**Expected changed/new file set (verify against `git status` before staging):**

| Status | Files |
|---|---|
| Modified | `PROJECT_COMPLETION_REPORT.md`, `DEPLOYMENT_GUIDE.md`, `docs/SECURITY.md`, `docs/CONTRIBUTING.md`, `frontend/locales/en.json`, `frontend/locales/my.json`, `frontend/app/contact/page.tsx`, `AI_VIDEO_RECAP_FINAL_PROJECT_REPORT.pdf` (regenerated) |
| New | `README.md`, `STEP7_GITHUB_PUBLIC_SETUP_PLAN.md`, `STEP8_PUBLIC_PUSH_PREPARATION_PLAN.md` (this file) |
| Unchanged (already committed) | Everything else, including `STEP5_PRE_COMMIT_AUDIT_REPORT.md` (historical snapshot — do NOT modify) |
| Never created | `LICENSE` (per owner decision) |

**Staging (NOT blind `git add -A`):**
1. Build the explicit file list from `git status --porcelain -uall` and verify it matches the table above exactly (count + names).
2. Stage via explicit literal pathspecs (`git add --pathspec-from-file=<verified-list>`, `:(literal)` prefix) — same method as the first commit.
3. Verify staged set:
   - `git diff --cached --stat` → file count + insertions match expectation.
   - `git diff --cached --name-status` → all entries `M`/`A`, no unexpected paths.
   - Staged-path forbidden check → no `.env`, credentials, keys, generated dirs, archives.
   - `python3 scripts/secret_scan.py` → exit 0, clean.
4. Commit (proposed message — needs CP-1/CP-3 approval):
   - `Docs: fix outdated Git claims, remove placeholder security contact, add root README (no license)`
5. Verify after commit:
   - `git log --oneline` → 2 commits on `main` (rewritten root + this commit; root hash = CP-2 hash if Phase 1 ran, else `99556ea`).
   - `git status --short` → clean.
   - `git remote -v` → still empty.

**STOP for CP-4.** Do not proceed to any push step without separate approval.

---

## Phase 5 — Pre-push verification (push NOT included)

Confirm all of the following, then STOP:
- [ ] `git log` shows 2 commits on `main`; root commit author = noreply address (if Phase 1 ran) or the original author (if Option A kept).
- [ ] `git status` clean.
- [ ] `git remote -v` empty (no remote yet).
- [ ] Secret scan clean.
- [ ] README contains all required sections incl. NOT READY banner, migration warning, no-license statement.
- [ ] PDF regenerated with updated git claim.
- [ ] No `securityEmail` / placeholder contact remains in source (grep checks pass).
- [ ] No `LICENSE` file exists.
- [ ] STEP 5 audit file unmodified.

**Push itself is OUT OF SCOPE for this plan** — it needs its own approval covering: repo creation (browser, signed-in `mm-video-recap`, Public, `main`, do NOT auto-add README/LICENSE/.gitignore), remote add (exact URL approval), and `git push -u origin main`.

---

## Risks

| Risk | Mitigation in this plan |
|---|---|
| Noreply address mistyped/guessed → wrong author on the rewritten commit | CP-1: owner confirms exact address from Settings; §1 step 5 verification before proceeding |
| Amend after push (email already public) | Phase 1 runs before any push; push is out of scope; never amend after push |
| Old-hash references (STEP 5/7/8 docs, prior messages) go stale after rewrite | Historical records intentionally NOT edited; new hash recorded at CP-2 and used from then on |
| Removing the security contact leaves no private reporting channel | SECURITY.md will state the channel (GitHub private vulnerability reporting) is enabled at repo creation — a follow-up step, not promised as already existing |
| Contact-page removal breaks the frontend build | tsc + build verification in §2e before commit |
| PDF pipeline cannot be re-established | STOP and report; do not ship the stale PDF |
| Wrong files staged in the second commit | Explicit literal pathspec list + staged-diff review (§4); never blind `git add -A` |
| Accidental push / remote creation | Push and remote steps are out of scope; CP-4 is a hard stop |

---

## Confirmation

- ✅ Only this plan file was created in STEP 8.
- ✅ No file modified, deleted, or otherwise created.
- ✅ No `git add` / commit / amend / reset / rebase / history rewrite.
- ✅ No remote add/set/remove. No GitHub repo creation. No push/pull/fetch.
- ✅ No GitHub Settings changes. No email changes.
- ✅ No deployment. No migration run.
- ✅ No secrets in this plan or in any terminal output.
- ⏸️ **Plan only. Stopped. Awaiting owner approval (CP-1) before any action.**

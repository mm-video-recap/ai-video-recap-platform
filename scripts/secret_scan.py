#!/usr/bin/env python3
r"""secret_scan.py — fail CI if anything key-like is committed (stdlib only).

Recursively scans the repo for secret-looking patterns, excluding:
  node_modules, .git, venv, *.lock files, and this script's own pattern docs.

Patterns:
  - Google API keys:            AIza[0-9A-Za-z_-]{10,}
  - Groq keys:                  gsk_[0-9A-Za-z]{10,}
  - OpenRouter keys:            sk-or-v1-[0-9A-Za-z]{10,}
  - Hugging Face tokens:        hf_[0-9A-Za-z]{10,}
  - Generic sk- keys:            sk-[0-9A-Za-z]{10,}  (length required so that
                                ordinary words containing 'sk-' don't match)
  - AWS access key ids:         AKIA[0-9A-Z]{16}
  - Private keys:               -----BEGIN [A-Z ]*PRIVATE KEY-----
  - Inline passwords:           password\s*=\s*["'][^"']{4,}["']
                                (.env.example is placeholder-only by design,
                                so it is skipped for this rule)
  - Slack tokens:               xox[bap]-

Prints file:line for every hit. Exit 1 on any hit, 0 when clean.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "__pycache__", ".next",
             "dist", "build", "out", ".hg", ".svn"}
SKIP_SUFFIXES = {".lock"}
SKIP_FILES = {"secret_scan.py"}  # this file documents the patterns itself

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{10,}")),
    ("groq-key", re.compile(r"\bgsk_[0-9A-Za-z]{10,}")),
    ("openrouter-key", re.compile(r"\bsk-or-v1-[0-9A-Za-z]{10,}")),
    ("huggingface-token", re.compile(r"\bhf_[0-9A-Za-z]{10,}")),
    ("generic-sk-key", re.compile(r"\bsk-[0-9A-Za-z]{10,}")),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("inline-password", re.compile(r"""password\s*=\s*["'][^"']{4,}["']""", re.IGNORECASE)),
    ("slack-token", re.compile(r"\bxox[bap]-[0-9A-Za-z-]+")),
]

# Lines that are obviously placeholders, not real secrets.
PLACEHOLDER_RE = re.compile(
    r"PLACEHOLDER|YOUR_|EXAMPLE|<[^>]*>|\bxxx+\b|\.\.\.", re.IGNORECASE)


def iter_files():
    for f in REPO.rglob("*"):
        if not f.is_file():
            continue
        if f.name in SKIP_FILES:
            continue
        if f.suffix in SKIP_SUFFIXES:
            continue
        rel_parts = f.relative_to(REPO).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        # skip obvious binaries
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
                                ".mp4", ".mp3", ".wav", ".pdf", ".zip", ".gz",
                                ".woff", ".woff2", ".ttf", ".eot", ".pyc"}:
            continue
        yield f


def main() -> int:
    hits: list[tuple[str, int, str, str]] = []
    for f in sorted(iter_files()):
        try:
            text = f.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        rel = str(f.relative_to(REPO))
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in PATTERNS:
                if name == "inline-password" and rel == ".env.example":
                    continue  # placeholder-only by design
                m = rx.search(line)
                if m and not PLACEHOLDER_RE.search(m.group(0)):
                    hits.append((rel, lineno, name, m.group(0)[:40]))

    if hits:
        print(f"secret_scan: {len(hits)} potential secret(s) found — FAIL")
        for rel, lineno, name, snippet in hits:
            print(f"  {rel}:{lineno}  [{name}]  {snippet}…")
        return 1
    print("secret_scan: clean — no key-like patterns found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

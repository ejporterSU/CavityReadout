# 003 — Set up the commit-log documentation folder

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-21

## What
Created `docs/commit-log/` with one markdown file per commit plus an `index.md`
table, and back-filled entries for the two prior commits (001, 002).

## Why
Requested a durable, human-readable record of what each commit did and why, so the
history is easy to review for future work without digging through diffs.

## Convention (followed going forward)
- One file per commit: `NNN-<slug>.md`, numbered in commit order.
- Each file: what changed, why, verification (if any), and notes for future work.
- The doc is committed **together with** the change it describes; its own hash is
  recorded as "this commit" since the hash isn't known until commit time.
- Keep `index.md` updated with a new row per commit.

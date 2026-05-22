# 004 — Add CLAUDE.md for cross-machine project memory

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-21

## What
Added a root `CLAUDE.md` capturing the portable project context, user context, and
working conventions (notably the commit-log convention).

## Why
Requested a way to persist these notes *with the project* so they carry across
different computers. Claude Code auto-loads `CLAUDE.md` into context each session,
and committing it to git makes it travel with any clone — unlike the machine-local
`~/.claude/...` memory, which never leaves the local computer.

## Notes for future work
- Kept machine-specific facts (shell choice, whether `gh` is installed) out of
  `CLAUDE.md` since they may not hold on another machine; those stay in local memory.
- If `CLAUDE.md` and local memory ever disagree, prefer the current repo/code state
  and update whichever is stale.

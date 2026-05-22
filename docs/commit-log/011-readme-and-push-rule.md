# 011 — Add README + "update README on every push" rule

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-22

## What
- `README.md` (new): top-level documentation of the project as it stands —
  overview, features, repository layout, requirements, how to run (incl.
  `--simulate`), a full tour of the GUI (shared controls, the three modes, the
  5000-point display cap, current startup defaults), and how to import the
  analysis/control layers from a notebook.
- `CLAUDE.md`: removed the old "No README by request" convention (superseded by
  the user's request) and added a README convention: keep `README.md` current and
  **update it on every push** to reflect what's being pushed, including that update
  in the push.

## Why
The user asked for a README documenting everything so far, and a standing rule that
future pushes also refresh the README so it never goes stale. The rule lives in
`CLAUDE.md` (loaded into context each session) alongside the commit-log convention,
since updating the README is a judgment task rather than a deterministic action.

## Verification
Docs-only change; README content cross-checked against the current code (rate
options in `gui.py`, defaults in `controller.py`, modes in `analysis_modes.py`,
analysis functions in `analysis.py`).

## Notes for future work
- The push rule is a documented convention, not an enforced hook. If a hard
  guardrail is wanted, a `git push` PreToolUse hook in `.claude/settings.json`
  could remind/refuse until the README is touched.

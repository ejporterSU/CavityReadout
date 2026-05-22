# CLAUDE.md

Project context and working conventions for the CavityReadout repo. Committed to git
so it persists across machines and sessions.

## Project
Python control + readout for a Cleverscope oscilloscope, used for heterodyne cavity
measurements (Kasevich Group, Stanford).
- `Cscope control driver/cscope_class.py` — `CScope`, the hardware wrapper (connect,
  time axis, trigger, per-channel range/coupling, acquisition).
- `Cscope control driver/controller.py` — `ScopeConfig` + `ScopeController` (+ `MockScope`
  for hardware-free simulation): a reusable, GUI-free control layer.
- `Cscope control driver/gui.py` — a simplified PyQtGraph readout app on top.
- `run_scope.py` — launcher (`--simulate` for no hardware).
- Analysis lives in Jupyter notebooks; keep new code easy to import/use from one.

Note: the vendor driver loads its DLL via a relative path and the DLL is not in the
repo, so hardware runs require it present; vendor modules use flat imports (the
`Cscope control driver` folder must be on `sys.path`).

## User
Stanford physicist (ejporter@stanford.edu), cavity QED / heterodyne work: cavity scans,
atom counting, noise-floor and side-of-fringe measurements. Strong numpy / scipy /
matplotlib / Jupyter fluency — frame explanations in physics/instrumentation terms.

## Conventions
- **Commit log:** every git commit gets a `docs/commit-log/NNN-slug.md` documenting what
  changed, why, verification (if any), and notes for future work — committed alongside
  the change, with `docs/commit-log/index.md` updated. See that folder for the format.
- No README by request; documentation goes under `docs/`.

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
- `Cscope control driver/analysis.py` — pure numpy/scipy analysis routines (e.g.
  `fit_lorentzian`, `compute_spectrum`), no Qt, so they import straight into a notebook.
- `Cscope control driver/analysis_modes.py` — the GUI's mode framework:
  `AnalysisMode` base + `FreeViewMode`, `LorentzianFitMode`, and `FFTMode` (live
  single-channel spectrum, amplitude/ASD, linear/dB, windowed). Add an analysis
  mode by subclassing `AnalysisMode` and registering it in `ScopeWindow.modes`.
- `Cscope control driver/gui.py` — a simplified PyQtGraph readout app on top, with a
  Mode selector that swaps between free viewing and analysis modes.
- `run_scope.py` — launcher (`--simulate` for no hardware).
- Analysis math lives in `analysis.py` (notebook-importable); keep new analysis code
  easy to import/use from a notebook the same way.

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
- **README:** keep `README.md` current. **Every time you push, first update `README.md`**
  to reflect the changes being pushed (features, controls, defaults, layout), and include
  that update in the push. Additional documentation still goes under `docs/`.

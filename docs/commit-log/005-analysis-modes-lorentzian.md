# 005 — Analysis-mode framework + Lorentzian fit

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-21

## What
Turned the single-view readout into a mode-switchable app and added the first
analysis mode (Lorentzian fit), the start of the data-analysis suite.

- `Cscope control driver/analysis.py` (new): pure numpy/scipy. `lorentzian(t, t0,
  fwhm, amp, offset)` and `fit_lorentzian(t, y)` → result dict with params, 1σ
  errors, R², RMS residual, the model curve, and a `success`/`message` pair.
  No Qt, so it's directly importable from a notebook.
- `Cscope control driver/analysis_modes.py` (new): the mode framework.
  `AnalysisMode` base (`build_panel`/`activate`/`deactivate`/`on_frame`/
  `set_running_state`) plus `FreeViewMode` (the original live view: Run/Stop/Single,
  autoscale, save, metrics) and `LorentzianFitMode` (channel picker + "Acquire &
  Fit" button + results readout; shows only the fitted channel and overlays a
  dashed fit curve). Modes operate on a host `ScopeWindow`, no `import gui`.
- `Cscope control driver/gui.py`: added a "Mode" selector + `QStackedWidget`;
  moved Run/Display/Save/metrics into `FreeViewMode`; the acquisition-mode combo
  became a shared "Acquisition" box; `_on_frame` now delegates to the active mode;
  `_set_running_state` delegates per-mode button enabling. Several handlers were
  made public (`start_continuous`, `start_single`, `stop_acquisition`,
  `autoscale_x/y`, `save_last`, `fmt_hz`) for modes to call. The control panel
  now lives in a `QScrollArea` (fixed 352 px wide) so it scrolls instead of
  squeezing widgets out of reach as more boxes/modes are added; default window
  height bumped to 720.
- `Cscope control driver/controller.py`: `MockScope` now emits a Lorentzian
  resonance on channel C (peak centered in the window, FWHM ≈ 8% of the span) so
  `--simulate` exercises the fit end-to-end; other channels unchanged.
- `requirements.txt`: added `scipy`.

## Why
The user is starting a data-analysis suite and wants to switch between free
viewing and analysis modes, beginning with fitting a Lorentzian (cavity-resonance
lineshape vs. the sweep axis) to a chosen channel. Because many more analysis
modes are coming, the design prioritizes a reusable mode interface — adding a new
mode is one `AnalysisMode` subclass registered in `ScopeWindow.modes`.

Per the user's choices: the fit is driven by a single "Acquire & Fit" button that
takes one acquisition (honoring the configured acq mode, so it can await a
trigger); analysis modes show only the relevant traces; the readout reports center
t0, FWHM, amplitude, offset (each ± 1σ) and R²/RMS.

## Verification
- Unit (`analysis.py`): synthetic noisy peak recovered t0/FWHM/amp within errors
  (R²≈0.99); dip recovered with negative amplitude (R²≈0.96); pure sine gave R²≈0.
- Headless GUI (`QT_QPA_PLATFORM=offscreen`): simulate mode, fit on channel C gave
  t0=3 ms, FWHM≈563 µs (mock truth 560 µs), amp=0.40 V; only channel C drawn with
  the fit overlay. Channel A (sine) showed the "poor fit" warning and R²=0. Mode
  switch back to Free View restored all four curves and removed the overlay.

## Notes for future work
- A converged-but-meaningless fit (low R²) is flagged with a "⚠ poor fit" warning
  rather than treated as a hard failure; only non-convergence returns
  `success=False`. Revisit the 0.8 R² threshold if it proves too strict/loose.
- FWHM/center are in time units. Cavity work will likely want a sweep→frequency
  calibration so linewidth and a Q-factor can be reported in Hz; that can be a
  per-mode option later.
- New analysis modes: subclass `AnalysisMode`, build a panel, handle `on_frame`,
  and append to `ScopeWindow.modes`. Shared scope config (connection/trigger/
  timebase/channels) stays in the always-visible part of the panel.

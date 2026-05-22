# 008 — Waveform display cap (5000 pts) + display/full save buttons

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-22

## What
Capped the number of points drawn per waveform trace and split the Free View save
into two buttons (displayed vs. full resolution).

- `Cscope control driver/gui.py`:
  - `ScopeWindow.MAX_DISPLAY_POINTS = 5000` and `decimate_display(t, y)` — stride
    decimation (`step = ceil(N/5000)`, `t[::step]`) returning ≤5000 points; short
    traces pass through untouched. Display-only: the stored capture stays full-res.
  - Replaced `save_last` with `save_full` / `save_display` (thin wrappers over
    `_save_capture(decimated)`). "Save full" writes `controller.last_capture` as-is;
    "Save display" writes the same stride-decimated trace that's shown (all four
    channels A–D, one shared step since they share `t`). Default filenames
    `capture_full.npz` / `capture_display.npz`.
- `Cscope control driver/analysis_modes.py`:
  - `FreeViewMode`: the single "Save last frame" button became a "Save (.npz)" box
    with **Save display** and **Save full** buttons (with tooltips).
  - All time-domain curve draws now go through `host.decimate_display(...)`:
    `FreeViewMode._draw` (all enabled channels) and the selected-channel draw in
    `LorentzianFitMode.on_frame` / `FFTMode.on_frame`.
  - Analysis is unaffected: `fit_lorentzian` and `compute_spectrum` still receive the
    full-resolution `channels[sel]`; only the drawn curve is decimated. The FFT
    spectrum keeps all its bins (capping it could hide narrow peaks).

## Why
The user wanted faster frame updates by drawing at most 5000 points per trace, while
keeping full data for analysis and saving — and a way to save either the displayed
(decimated) waveform or the full-resolution capture. Decimation is deliberately
display-only; the cap applies to the time-domain waveform, not the FFT (per the
user's choice — spectral decimation risks dropping narrow lines/beat notes).

## Verification
Headless (`QT_QPA_PLATFORM=offscreen`, simulate, N=200000 capture):
- `decimate_display` returned exactly 5000 monotonic points; all Free View curves
  drew ≤5000 (pyqtgraph's existing auto-downsampling reduces further for the view).
- "Save full" wrote 200000 samples; "Save display" wrote 5000 samples with arrays
  A–D present.
- In FFT View the spectrum kept all 100001 bins while the waveform draw was 5000.

## Notes for future work
- Decimation is plain stride (uniform). It can alias fast features in the *display*
  only; "Save full" / analysis are exact. If envelope fidelity on screen matters,
  swap in min/max-pair decimation (≈2× points, preserves peaks).
- `MAX_DISPLAY_POINTS` is a class constant; expose it as a control if a runtime
  cap is wanted.

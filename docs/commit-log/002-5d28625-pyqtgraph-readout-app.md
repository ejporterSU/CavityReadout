# 002 — Add simplified PyQtGraph readout app for the Cleverscope

- **Commit:** `5d28625ee9417c9b32db5ad9e398942b337075b6`
- **Date:** 2026-05-21

## What
A small desktop interface on top of `CScope` to set the settings that matter and
read out waveforms in auto / triggered / single mode, with both continuous live
run and one-shot capture. Built so the control layer is reusable from notebooks.

Files added (4, +706 lines):
- `Cscope control driver/controller.py`
  - `ScopeConfig` dataclass — all editable settings as plain values (rate, time
    window, per-channel range/coupling/enable, trigger, acq mode).
  - `ScopeController` — wraps `CScope`; `apply_config()` pushes the whole config
    in one call; `acquire_once(mode)` returns `(t, channels, metrics)` and stores
    `last_capture`. `connect()` lazily imports vendor code only on the real path.
  - `MockScope` — drop-in stand-in returning noisy sine waves (Ch D is a TTL-ish
    square) so the full app runs with no DLL/hardware via `simulate=True`. Caps
    synthetic frames at 200k samples for a smooth live loop.
- `Cscope control driver/gui.py`
  - PyQtGraph window: connection, run mode, trigger, time base, per-channel
    controls, live 4-trace plot, save-to-`.npz`.
  - `AcquisitionWorker(QThread)` runs blocking acquisition off the GUI thread;
    continuous loop emits frames, GUI only draws. Stop is a flag checked per frame.
  - Display: **Auto X (full range)** fits x to the frame's time span; **Auto Y
    (measured)** fits y to enabled-channel min/max. `HoverAxis` darkens an axis on
    hover to signal pyqtgraph's single-axis drag-zoom.
- `run_scope.py` — launcher fixing `sys.path` + working dir (vendor flat imports
  and the relative DLL path). `--simulate` flag.
- `requirements.txt` — numpy, pyqtgraph, PySide6.

## Why
First step toward replacing manual notebook driving with a simplified
Cleverscope-app-like interface, while keeping clean frames flowing into the
analysis workflow (`last_capture`).

## Verification
Verified in simulation only (no hardware/DLL available): headless controller test
and offscreen-Qt smoke tests — connect, single capture, continuous run + clean
stop, channel enable/disable clears curves, metrics update, Auto X/Y set correct
ranges, hover darken/restore. Real-hardware path (`--simulate` off) untested.

## Notes for future work
- Heterodyne demod / Lorentzian fitting / IQ plots stay in the analysis layer;
  v1 only delivers frames. A notebook example wiring `ScopeController` in is a
  natural next step.
- Mock `fs` reads lower than the configured rate because of the 200k-sample cap —
  simulation artifact only; real hardware won't cap.

# 013 — VRS–cavity alignment sweep analysis mode

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-06-01

## What

Added a new analysis mode, **VRS Alignment**, for aligning an atomic (VRS)
frequency to a bare-cavity frequency by sweeping the cavity length externally and
reading off the cavity frequency where the doublet/single asymmetry crosses zero.

### Analysis math — [analysis.py](Cscope%20control%20driver/analysis.py) (Qt-free, notebook-importable)
- `single_lorentzian(t, A, x0, gamma, offset)` and
  `double_lorentzian(t, A1, x1, g1, A2, x2, g2, offset)` — peak models (`gamma` =
  FWHM), ported from the `CleverscopeTesting.ipynb` helpers.
- `segment_ttl(t, ttl, threshold, min_width=0.0)` — pairs rising→falling TTL edges
  into `(start, stop)` index windows; drops edge-touching pulses (TTL already high
  at `t[0]` or still high at `t[-1]`) and sub-`min_width` pulses. A refinement of
  the notebook's `split_signal`.
- `fit_window_asymmetry(t, sig, ttl, scale_khz_per_s, threshold=1.0, min_width=0.0,
  gof_min=0.5, factor=1.0)` — the core routine. Requires exactly two TTL windows
  (window 1 → double, window 2 → single). Re-zeros each window to its own start so
  the peak position *within its ramp* is what maps to frequency; seeds peaks
  amplitude-relative via `scipy.signal.find_peaks` with a split-window argmax
  fallback; bounded `curve_fit`; gates on `min(R²_double, R²_single) ≥ gof_min`.
  Returns a dict (mirrors `fit_lorentzian`): `asymm_khz = factor · scale_khz_per_s ·
  (center_double − center_single)` with a covariance-propagated `asymm_err_khz`,
  plus per-window data/model arrays for plotting. Never raises — returns
  `success=False` + a reason on any failure.

### GUI mode — [analysis_modes.py](Cscope%20control%20driver/analysis_modes.py)
New `VRSAlignmentMode(AnalysisMode)`, registered in
[gui.py](Cscope%20control%20driver/gui.py) `ScopeWindow.modes`. Panel controls:
- **Channels:** Signal + TTL channel dropdowns (default TTL = the configured
  trigger channel, signal = first other enabled channel).
- **Time window (crop):** start/stop (ms); `stop ≤ start` means "use the whole
  capture". Crops the captured trace before segmentation — it does *not*
  reconfigure the scope.
- **TTL gating:** threshold (V), min pulse width (ms).
- **Scan scaling:** scan range (MHz) + scan time (ms) → `scale_khz_per_s =
  (range / time) · 1e-3`.
- **Cavity sweep:** start (MHz), step (MHz), num steps, min R².
- **Start Analysis** / **Reset**, a live **Total time** label, a status line, and a
  result line.

Sweep driving: Start Analysis forces the acquisition mode to **Triggered** and
arms a *continuous* run, so the `AcquisitionWorker` re-arms a triggered capture
after each frame (timeouts in continuous mode harmlessly retry). Every *successful*
shot becomes the next sweep point at `start + k·step` MHz; failed shots
(wrong TTL count, short window, bad/low-R² fit) are reported and do **not** advance,
so the operator can retrigger at the same cavity setting. After `num_steps` valid
points the mode does a weighted `np.polyfit` (1/σ weights), computes the
zero-crossing `−c/m`, propagates the covariance to its uncertainty, and reports the
optimal cavity frequency.

The fit overlays (double = red dash, single = magenta dash) are drawn on the signal
channel's ViewBox; the asymmetry-vs-cavity-frequency scatter + error bars, the line
fit, and a vertical zero-crossing marker are drawn on the shared bottom (FFT) pane,
which the mode relabels on activate and restores on deactivate.

## Why

The lab aligns a vacuum-Rabi-split (VRS) doublet to a bare-cavity resonance by
walking the cavity length. Each triggered shot captures both a VRS doublet and a
bare-cavity reference under TTL gating; the time gap between the doublet midpoint
and the single peak (scaled to kHz by the scan rate) is the alignment error, and it
moves linearly with cavity frequency. Plotting it vs. the externally-stepped cavity
frequency and reading the zero-crossing gives the cavity frequency to dial in. This
existed only as loose notebook functions (`get_asymmetry`/`split_signal`); promoting
it to a first-class analysis mode (with the math in `analysis.py` so a notebook can
still import it) matches the repo's mode framework and makes it usable live.

## Verification

No hardware. Two offscreen/headless harnesses:

- **Math:** synthetic shots (two clean TTL windows; double then single Lorentzian
  whose doublet-vs-single center offset varies linearly with a simulated cavity
  frequency) recovered each per-step asymmetry to ≈0.1 kHz and the weighted
  zero-crossing to within ~0.01–0.04 MHz of the injected value. 1-TTL, 3-TTL, and
  flat-signal shots returned `success=False` with the expected reasons; an
  edge-touching leading TTL pulse was correctly dropped, leaving a valid 2-window
  fit.
- **GUI (Qt offscreen):** built the real `ScopeWindow(simulate=True)`, switched to
  VRS Alignment — secondary pane shown and relabelled "Cavity frequency (MHz)" /
  "Asymmetry (kHz)"; the not-connected guard fired; an 11-step `on_frame`-driven
  sweep finalized with 11 scatter points and a zero-crossing of 49.99 MHz (true
  50.0); a 1-TTL shot incremented the failure count without advancing; Reset cleared
  state; switching away restored the FFT pane's original "Frequency"/"Hz" labels and
  hid it.

## Notes for future work

- The sweep advances on every successful trigger, so the trigger must fire once per
  cavity setting. If the TTL free-runs faster than the operator retunes, add a
  minimum-dwell guard (ignore frames arriving within N seconds of the last accepted
  one) — the hook is a single check at the top of the sweep branch in `on_frame`.
- `MockScope` does not emit the two-window double/single pattern, so a live
  `--simulate` run will report per-shot failures (expected); extending `MockScope`
  with an optional VRS test pattern would allow a fully live demo.
- Peaks are assumed positive (amplitudes bounded ≥ 0). A dip-mode toggle would be a
  small change to the seeding/bounds in `fit_window_asymmetry`.

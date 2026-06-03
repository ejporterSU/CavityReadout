# 014 — Heterodyne signal + IQ-demodulation viewer

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-06-03

## What

A new, standalone, deliberately bare-bones app for viewing and demodulating
heterodyne measurements — separate from the main `gui.py` readout. Built up over
several steps this session: raw four-channel viewer → navigator → channel-A
magnitude band → two-tone simulation → IQ demodulation → frame-drop gating.

### New files
- [run_heterodyne.py](../../run_heterodyne.py) — launcher, mirrors `run_scope.py`
  (puts `Cscope control driver/` on `sys.path`, `chdir`s to the repo root for the
  vendor DLL). `--simulate` / `-s`.
- [heterodyne_viewer.py](../../Cscope%20control%20driver/heterodyne_viewer.py) —
  the whole app: mock, controller subclass, acquisition worker, and the window.

### Reused analysis math — [analysis.py](../../Cscope%20control%20driver/analysis.py) (Qt-free, notebook-importable)
- `envelope(y)` — amplitude envelope via `|hilbert(y - mean)|`.
- `dominant_frequency(y, fs, fmin=0, fmax=None)` — peak rFFT-magnitude frequency
  (ex-DC); used to detect the B and C tones.
- `demodulate_beatnote(het, ref, f_center, fs, f_bw=500e3, f_lp=100e3, digital_mix=False)`
  — ported from the `CleverscopeTesting.ipynb` `digital_mix=False` path: 4th-order
  Butterworth bandpass of `het` and `ref` around `f_center` (`sosfiltfilt`),
  normalize `ref` by its central-window amplitude, `hilbert` → quadratures, mix,
  4th-order lowpass (`filtfilt`); returns `(4(I²+Q²), atan2(Q,I), I, Q)`. Returns
  zero arrays (no crash) when the band is unusable for the sampling rate
  (`f_center<=0` or `f_center+f_bw/2 ≥ Nyquist`).

### The viewer — `heterodyne_viewer.py`
- **Fixed channel roles:** A heterodyne beat, B/C RF tones (mixed for the demod
  reference), D TTL gate. All four always read.
- **Controls:** Connection; Measurement *duration* (window = duration ±100 µs
  guard); Sampling rate (400 MHz…1 MHz, default 50 MHz); per-channel **Scale (±)**
  magnitude dropdowns (10 mV…5 V) instead of min/max; **Demod** bandpass-BW /
  lowpass-cut fields (kHz) + a detected-frequency readout; Run / Single / Stop.
  Defaults: A/B/C AC at ±1 V, D DC at ±5 V; trigger D rising; 3 ms duration.
- **Left plot column:** four stacked channels. A/B/C share one X range; **D is a
  fixed full-window navigator** carrying a `LinearRegionItem` whose region drives
  the X view of A/B/C *and* the demod plots (region↔A-view kept in sync both ways,
  guarded against re-entrancy). D also shows a light-gray ± band = `envelope(A)`
  (the *total* channel-A magnitude), scaled so A's full-scale maps to D's range —
  a navigation aid for placing the region.
- **Right plot column (demod):** a Magnitude `4(I²+Q²)` plot and a Phase
  `atan2(Q,I)` plot, each overlaying both beat tones (`f_B−f_C`, `f_B+f_C`), both
  X-linked to channel A so they follow the navigator zoom.
- **`HeterodyneController(ScopeController)`** overrides only `connect()` to use the
  heterodyne mock in simulate mode; the real-hardware path is inherited.
- **`HeterodyneMockScope`** synthesizes A = two tones at `F_B∓F_C` (3.5 / 4.5 MHz)
  each with its own Lorentzian envelope offset by ~1 HWHM, B = 4 MHz, C = 0.5 MHz,
  D = a 3 ms TTL pulse framed by the guard band.

### Frame-drop gating — `DemodAcquisitionWorker`
A dedicated acquisition `QThread` (the viewer no longer imports `gui.AcquisitionWorker`).
In continuous mode it hands off a frame and **waits** (`threading.Event`) until the
GUI has finished drawing + demodulating it before acquiring again — intervening
triggers are dropped, not queued. `_on_frame` releases the gate in a `finally` so a
demod error can't hang the loop; `stop()` also releases it for a clean stop.

## Why

The viewer is the first piece of a heterodyne *processing* tool. Signal A carries
two beat tones at `f_B ± f_C`; multiplying B·C reproduces those sidebands as a
phase reference, so IQ-demodulating A against the bandpassed/normalized reference
recovers each tone's amplitude (`4(I²+Q²)`) and phase (`atan2(Q,I)`) vs time — the
quantities the lab actually wants. Keeping the math in `analysis.py` lets a
notebook run the identical pipeline. The gating was added because the per-frame
demod is heavy: on `Auto`/continuous it overlapped the acquisition's own wait loop,
starving it into a 10 s timeout and backing up the frame queue; serializing
acquire→analyze removes both.

## Verification

No hardware. Headless harnesses (`QT_QPA_PLATFORM=offscreen`), each run and then
deleted:

- **Signals/envelope:** simulated frame has the right tones (A peaks at 3.5/4.5 MHz;
  `dominant_frequency` returns B≈4.0, C≈0.5 MHz); the D gray band tracks `envelope(A)`,
  is symmetric, stays in D's range, scales to A's magnitude, and rails to D's top
  when A is clipped at a 100 mV scale.
- **Navigator:** all four X-axes start on the full window (guard included); D's X
  mouse is disabled; dragging the region zooms A/B/C (and demod plots) while D stays
  fixed; panning A moves the region back; changing duration resets everything to the
  new window.
- **Demod:** `demodulate_beatnote` at 3.5 and 4.5 MHz recovers the two Lorentzians;
  their magnitude peaks are separated by ≈1 HWHM (upper later), magnitude ≈ recovered
  amplitude² (~0.24 V² for a 0.5 V tone); a 5 MHz sampling rate returns zeros (guard).
- **Gating:** in a continuous run the worker stays ≤ 1 acquisition ahead of what the
  GUI has processed (strictly gated, never racing); Stop halts it cleanly; Single
  processes exactly one frame and draws the demod curves.

## Notes for future work

- The demod runs on the **GUI thread** in `_on_frame` (two bandpass+Hilbert+lowpass
  passes plus the envelope over the full capture, ≈0.3–1 s for 160k samples), so the
  window is briefly unresponsive each frame and continuous refresh is ~1–3 Hz. Moving
  the demod *into* `DemodAcquisitionWorker` (emit ready-to-draw results; pass filter
  params in thread-safely) would keep the UI responsive and still drop frames — the
  cleaner long-term fix.
- Filter params are user-set; there is no auto-clamp against the tone separation
  (`2·f_C`). A too-wide bandpass will bleed the other sideband in. Sensible defaults
  (500 kHz / 100 kHz) work for the simulated 1 MHz separation.
- Phase is recovered relative to the `B·C` reference, so a fixed quadrature offset
  between A's sine tones and ref's cosine sidebands shows up as a constant phase; the
  simulation has no intentional phase evolution to demo beyond that.

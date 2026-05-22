# 007 — FFT View mode (single-channel spectrum analyzer)

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-22

## What
Added an on-demand FFT viewer as a new analysis mode. When "FFT View" is selected
the right pane splits vertically: the waveform compresses into the top ~2/3 and a
frequency-domain plot occupies the bottom ~1/3. Picking any other mode hides the
FFT pane and the waveform reclaims full height.

- `Cscope control driver/analysis.py`: new `compute_spectrum(t, y, window, scaling)`
  (pure numpy, notebook-importable like `fit_lorentzian`). One-sided `rfft` with
  correct window normalization:
  - `scaling="amplitude"` → peak amplitude per bin (V): `2·|Y|/ΣS₁`, DC/Nyquist not
    doubled. An on-bin sinusoid of amplitude A reads A regardless of window.
  - `scaling="asd"` → amplitude spectral density (V/√Hz): `√(2·|Y|²/(fs·ΣS₂))`.
  - Returns `f, mag, units, fs, df, enbw, nyquist` plus a `success`/`message` pair.
  - Windows: rectangular / Hann / Hamming / Blackman.
- `Cscope control driver/analysis_modes.py`: new `FFTMode(AnalysisMode)`. Owns a
  curve on the host's FFT plot. Panel: Run/Stop/Single (live spectrum), Channel
  picker (one signal), Quantity (Amplitude V / ASD V/√Hz), Scale (Linear / dB),
  Window selector, frequency Min/Max (MHz) + "Full (Nyquist)", and "Auto Y". Shows
  only the selected channel on the time plot (like `LorentzianFitMode`); readout
  reports fs, Nyquist, df, ENBW, and the active window. dB conversion is display-only
  (`20·log10(mag)`, floored at peak·1e-12) so the stored spectrum stays physical;
  axis label switches to `dBV` / `dB(V/√Hz)` accordingly.
- `Cscope control driver/gui.py`: `_build_plot` now wraps the time plot and a new
  hidden `fft_plot` in a vertical `QSplitter` (`self.plot_splitter`); `show_fft_panel`
  reveals it at ~2:1 sizing. Registered `FFTMode` in `ScopeWindow.modes`.
- `Cscope control driver/gui.py` (run-state fix): the continuous-run flag is now
  tracked on the window (`self._continuous`) instead of being passed as a transient
  arg to `_set_running_state`. Previously `_on_mode_changed` re-applied the run state
  without the flag (defaulting `continuous=False`), so switching analysis modes while
  a continuous Run was active grayed out Stop (needs `running and continuous`) *and*
  Run/Single (need `not running`) with no way to recover. Now the flag is set when a
  run starts, cleared when it ends, and read by every `_set_running_state` call.

## Why
Cavity/heterodyne work cares about frequency content — beat notes, noise floors,
side-of-fringe spectra — as much as the trace. Per the user's choices: one signal at
a time; both amplitude (V) and ASD (V/√Hz) selectable with a linear/dB toggle on top;
live update during Run; a window-function selector as the "resolution" control (true
df = fs/N is fixed by record length, so the readout exposes df and ENBW rather than
pretending to add resolution); and an Auto-Y button on the FFT plot.

## Verification
- Unit (`analysis.py`): on-bin sinusoid (A=0.7, offset 0.05) read peak=0.7000 and
  DC=0.0500 across all four windows; off-bin tone read low as expected (scalloping
  loss). White-noise ASD median ≈1.18e-3 V/√Hz for σ=1 at fs=1 MHz, matching
  `√(ln2)·√(2/fs)` and independent of N.
- Headless GUI (`QT_QPA_PLATFORM=offscreen`, simulate): three modes registered;
  FFT pane hidden at start, shown on selecting FFT View, hidden again on switching
  back to Free View. A simulated frame rendered the spectrum curve; Linear↔dB,
  Amplitude↔ASD, Auto-Y, and Full (Nyquist) all ran without error.
- Run-state fix (headless): started a continuous Run, switched modes mid-run, and
  confirmed Stop stayed enabled (`run=False, stop=True, single=False`) instead of
  graying out; after Stop, Run/Single re-enabled.

## Notes for future work
- Live spectra are single-frame (no averaging). For noise-floor measurements,
  Welch-style averaging (running mean of PSD over frames) would cut variance — a
  natural follow-up, ideally added to `compute_spectrum` so notebooks share it.
- Frequency axis is linear; a log-frequency option could be added if wide-band
  spectra need it.
- dB reference for amplitude is 1 V (dBV); ASD dB is referenced to 1 V/√Hz. Revisit
  if a different reference (e.g. dBm into 50 Ω) is wanted.

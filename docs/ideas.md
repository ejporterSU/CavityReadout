# Ideas & Roadmap

Research notes and brainstorming for the Cleverscope readout app. Grouped by theme;
each item has a rough **priority** (★ high / ◆ medium / ○ nice-to-have) and **effort**
(S/M/L). Nothing here is committed work — it's a menu to pick from.

Most vendor-capability claims below were checked against the spec/driver files:
`SetupSignalGenerator` (`Cscope control driver/CleverscopeInterface.py`),
`WaveformAverages` / `AcquireMode` / `SamplerResolution` (`T_AcquireSpec.py`),
per-channel filters and probe gain (`T_ChannelSpec.py`), and the read-back helpers
`DisplayHardwareInfo` / `probe_settings` / `GetTriggerSettings` (`cscope_class.py`).

## 1. Display decimation, buffering & performance

Goal: full-resolution data always retained; the screen never lies about resolution;
no freezes.

- **★ S — Make display decimation peak-preserving.** The current `decimate_display`
  (`gui.py`) is plain stride (`t[::step]`), which can *hide* fast features on screen
  (a spike between kept samples vanishes) even though Save-full keeps them. Scopes
  solve this with min/max ("peak-detect") decimation. pyqtgraph already does this via
  `setDownsampling(mode='peak', auto=True)` + `setClipToView(True)` (already set on the
  time curves). Cleanest fix: **stop hand-decimating and feed pyqtgraph the full
  trace**, letting its peak-mode auto-downsampler handle the display — it decimates to
  the *view*, preserves peaks, and is C-fast. Keep an explicit cap only if a hard ceiling
  is wanted; if so, use min/max pairs, not stride.
- **★ S — Show the resolution honestly on-screen.** Add a one-line annotation:
  `N = 200,000 acquired · fs = 1 MHz · dt = 1 µs · showing ~5000 pts (peak)`. Removes
  any "what am I actually looking at" doubt. The acquired-side numbers already exist in
  `acquisition_metrics()` (`controller.py`); add the displayed-points count.
- **★ S — Display ADC bit depth.** Surface `SamplerResolution` / `DisplayHardwareInfo`'s
  ADC resolution so "resolution" (bits) is never conflated with sample count or df.
- **◆ M — Throttle redraw to a fixed FPS.** If frames ever arrive faster than the eye
  needs, cap GUI redraws (~30 FPS) and always draw the latest frame; drop intermediate
  ones. Prevents the event loop from drowning in setData calls. (Worker already off the
  GUI thread — this guards the draw side.)
- **◆ M — Keep heavy compute off the GUI thread / bound it.** FFT in `FFTMode.on_frame`
  runs an `rfft` on the *full* capture on the GUI thread every frame. Fine at N=1e5,
  but at N=4e6 it can stutter. Options: cap FFT input length, compute on the worker, or
  decimate-for-FFT with an explicit, labeled bandwidth. (Spectral decimation must be
  labeled — never silently.)
- **◆ M — Acquisition watchdog.** Known gap: if a blocking DLL call hangs, the worker's
  `finished` never fires and buttons stay disabled. Add a timeout/watchdog that resets
  UI state and surfaces an error if a frame doesn't arrive within N×(expected time).
- **○ M — Optional rolling frame buffer.** Keep the last K full-res frames in memory
  (ring buffer) for "scroll back" / averaging / export, distinct from `last_capture`.

## 2. Vendor features worth surfacing (important, not fancy)

- **★ M — Signal generator panel.** The scope has a built-in function generator
  (`SetupSignalGenerator(freq, amp, duty, waveform)` + `SigGenOffset`; sine/triangle/
  square/DC, 0.003 Hz–10 MHz, 0–8 Vpp, ±5 V offset). For cavity work this can *drive the
  sweep / inject a calibration tone* instead of needing external gear. High value.
- **★ M — Hardware waveform averaging.** `AcquireMode=WaveformAvg` with
  `WaveformAverages∈{1,4,16,64,128}` averages in the unit → lower noise floor for free.
  Directly serves the group's noise-floor / side-of-fringe measurements. Add an
  "Averages" selector; needs `NumBuffers ≥ averages+1`.
- **★ S — Hardware info / connection readout.** `CScope.DisplayHardwareInfo()` already
  returns serial, model, **ADC resolution**, channel count, siggen type. Show it on
  connect — confirms the right unit and the resolution in one place.
- **◆ S — ADC sampler resolution control.** Expose `SamplerResolution` (8/10/12/14/16-bit).
  Trade speed vs. vertical resolution explicitly (and label it so it's not confused with
  sample count).
- **◆ S — Per-channel bandwidth limit / filters.** The 20 MHz analog pre-filter and the
  MA/exponential `FilterOption` presets (`T_ChannelSpec`) cut HF noise — useful for clean
  low-frequency cavity signals. A simple per-channel "BW limit" checkbox is low effort.
- **◆ S — Probe gain per channel.** `T_Probe` (x1..x1000). If a probe/attenuator is used,
  the wrong setting silently mis-scales volts — a real "confusion" risk. Add a probe-gain
  selector that feeds the displayed voltage scaling.
- **◆ M — External / digital trigger + trigger filter.** Trigger source already supports
  External and Digital (`T_TrigChannel`), plus a trigger noise filter
  (`TriggerFilter`: LowPass/HiPass/Noise) and `ExtTrigThreshold`. Surfacing external
  trigger is valuable for synchronizing to lab electronics.
- **○ M — Sequential frame capture.** `NumSeqFrames` + `TransferSize_Sequence` grab many
  frames back-to-back with little dead time — good for repeated cavity scans/statistics.
- **○ S — Read-back helpers.** `probe_settings()` / `GetTriggerSettings()` already exist;
  wire a "sync from hardware" button so the panel can reflect the scope's actual state.

## 3. New analysis ideas (physics-oriented)

Most fit cleanly as new `AnalysisMode` subclasses (the framework makes this one class +
registration in `ScopeWindow.modes`).

- **★ M — Welch-averaged PSD / noise floor.** Running average of the spectrum across
  frames (already flagged as FFT follow-up). Cuts variance, gives a real V/√Hz noise
  floor — the natural companion to the existing FFT mode for noise work.
- **★ M — Exponential ring-down fit.** Fit `A·exp(-t/τ)+c` to a cavity ring-down →
  decay time τ, hence cavity linewidth/finesse. Mirror `fit_lorentzian` in `analysis.py`
  (pure numpy/scipy, notebook-importable) + a mode. High relevance to cavity QED.
- **★ S — On-plot cursors & measurements.** Two draggable cursors giving Δt, ΔV, and
  1/Δt (frequency). The single most useful day-to-day scope feature. pyqtgraph
  `InfiniteLine` makes this easy; can live in Free View or a shared overlay.
- **◆ M — I/Q (lock-in) heterodyne demod.** Mix the signal with cos/sin at a chosen
  carrier, low-pass → amplitude & phase vs time. Tailored to heterodyne cavity readout
  (beat-note amplitude/phase tracking).
- **◆ M — Spectrogram / waterfall.** FFT vs time as a heatmap to watch a beat note drift
  — pyqtgraph `ImageItem`. Good for alignment/drift diagnostics.
- **◆ S — Spectral peak tracker.** In FFT mode, auto-find the dominant peak; report its
  frequency, amplitude, and SNR; optionally log it over time.
- **◆ S — Region statistics.** Mean / RMS / std / Vpp / SNR over a selected x-range,
  plus a "side-of-fringe" slope (dV/df) readout the user explicitly cares about.
- **○ M — More lineshapes.** Gaussian and sine fits (sine fit → precise frequency/
  amplitude/phase), reusing the `fit_*` dict pattern.
- **○ L — Allan deviation / long-term frequency stability** for the beat note.

## 4. General UI improvements

- **★ S — Pause/freeze display** without stopping acquisition (inspect the current
  frame; underlying capture already retained).
- **★ S — Acquisition status + frame counter + live FPS** in the status bar
  (Running / Waiting-for-trigger / Stopped), so it's obvious whether triggers are
  arriving. Pairs with the watchdog (§1).
- **★ S — Save/load config presets.** Persist `ScopeConfig` to JSON and reload — stop
  re-dialing the panel each session. `ScopeConfig` is a dataclass, so this is small.
- **◆ S — Keyboard shortcuts** (Space = Run/Stop, S = Single, A = autoscale).
- **◆ S — Better autoscale.** Per-channel autoscale and a "fit all" that respects only
  enabled channels (extends existing `autoscale_y`).
- **◆ M — Dockable/tear-off panels.** `QDockWidget` for the FFT/analysis pane so it can
  be resized or popped out. (Borderline "fancy" — low priority.)
- **◆ S — Error/log strip.** A small scrollback for failures instead of only the
  single-line status label, so transient timeouts aren't missed.
- **○ S — Light/dark theme toggle.**

## Suggested first picks (high value / low effort)
1. Peak-preserving display decimation + on-screen resolution annotation (§1) — kills the
   "resolution confusion" worry directly.
2. On-plot cursors & Δt/ΔV/frequency readout (§3).
3. Hardware-info readout incl. ADC bits on connect (§2).
4. Signal-generator panel and hardware averaging (§2) — biggest new measurement
   capability for cavity/noise work.
5. Save/load config presets + pause/freeze + status/FPS (§4) — quality-of-life.

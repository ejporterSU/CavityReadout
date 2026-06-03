# CavityReadout

Python control + readout for a [Cleverscope](https://www.cleverscope.com/) USB
oscilloscope, used for heterodyne cavity measurements in the Kasevich Group
(Stanford): cavity scans, atom counting, noise-floor and side-of-fringe
measurements.

It provides a small, reusable control layer over the vendor driver, a set of
Qt-free analysis routines that import straight into a Jupyter notebook, and a
PyQtGraph desktop app that puts live acquisition and analysis modes behind one
window. Everything runs hardware-free in **simulation mode**, so you can develop
and demo without a scope attached.

---

## Features

- **Live readout** — continuous (`Run`) or one-shot (`Single`) acquisition of up
  to four channels, drawn on a fast PyQtGraph plot. **Every channel has its own
  ViewBox**, so each one renders at its own programmed range — zooming A does
  not rescale B (and zooming C does not rescale D). A/B share the **left**
  axis (whichever was pressed last is what the tick labels mean); C/D share
  the **right**. Mouse drag-zoom on the plot is display-only — it never
  changes the programmed acquisition window or channel range.
- **Mode-switchable analysis** — a Mode selector swaps the bottom of the control
  panel and what the plot shows:
  - **Free View** — every enabled channel, with autoscale and save.
  - **Lorentzian Fit** — fit a peak/dip Lorentzian to one channel and report
    center, FWHM, amplitude, offset (each ±1σ), plus R²/RMS.
  - **FFT View** — a live single-channel spectrum analyzer in a bottom split
    pane (amplitude V or ASD V/√Hz, linear or dB, selectable window).
  - **VRS Alignment** — sweep the cavity frequency (stepped externally) and fit
    each triggered shot's two TTL-gated windows (a double Lorentzian doublet, then
    a single bare-cavity peak). Plots the doublet-vs-single asymmetry (kHz) vs.
    cavity frequency, line-fits it, and reports the zero-crossing — the cavity
    frequency where the atomic line is aligned.
- **Notebook-friendly analysis** — `analysis.py` is pure numpy/scipy (no Qt), so
  the same math the GUI uses imports directly into a notebook.
- **Simulation mode** — `--simulate` synthesizes a heterodyne-flavored test
  pattern (A/B: ±1 V sine I/Q pair at 10 kHz; C: 1 ms train of 200 µs-FWHM
  Lorentzian peaks; D: 0/+2 V TTL trigger reference) at *absolute* amplitudes
  independent of the programmed range, so zooming behaves the same as on real
  hardware (tightening a range below the signal rails the trace). The whole app
  runs with no DLL or hardware.

---

## Repository layout

```
run_scope.py                     Launcher (sets sys.path + cwd, then opens the GUI)
requirements.txt                 numpy, scipy, pyqtgraph, PySide6
CLAUDE.md                        Project context + working conventions (for AI assistants)
CleverscopeTesting.ipynb         Scratch/exploration notebook
Cscope control driver/
  cscope_class.py                CScope: the hardware wrapper (connect, time axis,
                                 trigger, per-channel range/coupling, acquisition)
  controller.py                  ScopeConfig + ScopeController (+ MockScope): a
                                 reusable, GUI-free control layer
  analysis.py                    Pure numpy/scipy analysis (fit_lorentzian,
                                 compute_spectrum, fit_window_asymmetry) — no Qt,
                                 notebook-importable
  analysis_modes.py              Mode framework: AnalysisMode base + FreeViewMode,
                                 LorentzianFitMode, FFTMode, VRSAlignmentMode
  gui.py                         The PyQtGraph readout app (ScopeWindow)
  CleverscopeInterface.py, T_*.py, Cleverscope*.py
                                 Vendor driver + examples (flat imports)
docs/commit-log/                 One file per commit documenting what/why (see index.md)
```

---

## Requirements

- Python 3.9+
- `pip install -r requirements.txt` (numpy, scipy, pyqtgraph, PySide6)
- **For real hardware only:** the Cleverscope vendor DLL
  (`Cscope control driver/Cscope control driver 64.dll`) and a connected scope.
  The DLL is *not* in the repo and is loaded by a relative path, so it must be
  present for hardware runs. Simulation mode needs nothing but the Python deps.

---

## Running

```bash
python run_scope.py             # real hardware (needs the DLL + scope)
python run_scope.py --simulate  # synthetic data, no hardware
```

`run_scope.py` handles the two environment quirks the vendor driver needs: it puts
`Cscope control driver/` on `sys.path` (the vendor modules use flat imports) and
sets the working directory to the repo root (so the DLL's relative path resolves).

---

## Using the GUI

The left panel holds the shared scope settings; the right pane is the live plot.

**Always-visible controls**

- **Connection** — serial number + Connect/Disconnect; status line.
- **Acquisition** — acq mode: `Auto`, `Triggered`, or `Single`.
- **Trigger** — channel, level (V), slope (Rising/Falling).
- **Time base** — sampling rate (400 MHz … 100 kHz) and the resulting sample
  count `N`. The actual window (start/stop) is set with the time cluster on
  the plot (see below).
- **Channels** — per row: enable checkbox, color-coded channel label, AC/DC
  coupling. The per-channel voltage range is set with the cluster overlaid on
  the matching plot corner (see below).
- **Mode** — selects the analysis mode.

**On the plot (zoom / pan / reset clusters):**

Each axis has a 5-button cluster pinned to it. The button labels describe how
the **signal** moves on screen, not the underlying range:

- `-` zoom out 1.5×, `+` zoom in 1.5×, `R` reset to the startup value.
- For voltage: `v` pans the signal down by ¼ span, `^` pans it up.
- For time: `<` pans the signal left in the window, `>` pans it right.

Placement:

- **A (red)** → top-left of plot, **B (blue)** → bottom-left
  (both drive the **left** Y-axis).
- **C (green)** → top-right, **D (orange)** → bottom-right
  (both drive the **right** Y-axis).
- **Time** → centered horizontally just below the bottom axis.

Each Y-axis is tinted *and relabeled* (`Voltage A` / `Voltage B` on the left,
`Voltage C` / `Voltage D` on the right) to whichever channel on its side was
pressed most recently. The tick labels always belong to a single named
channel, and that channel's ViewBox is what mouse-drag on the axis
manipulates. Pressing the other channel on the same side leaves the displayed
range of the first untouched — only its own ViewBox moves.

Mouse pan/zoom on the data area stays display-only; only the cluster buttons
move the underlying programmed config that gets pushed to hardware.
Endpoints are silently clamped at ±100 V (and to ≥ 2 samples for the time
window).

**Default startup config:** ±2.5 V DC-coupled on all four channels, 1 MHz
sampling, a ±500 µs window (N = 1000 samples). The Reset (`R`) button on each
cluster returns it to whatever the config was at window startup.

### Modes

- **Free View** — Run / Stop / Single, Auto X / Auto Y, and two save buttons:
  - *Save display* → the decimated trace as shown (≤ 5000 points/channel)
  - *Save full* → the full-resolution capture

  Both write a `.npz` with `t, A, B, C, D`.
- **Lorentzian Fit** — pick a channel and click *Acquire & Fit*. Shows only the
  fitted channel with a dashed model overlay and a readout of center t₀, FWHM,
  amplitude, offset (±1σ), R², and RMS residual. A low R² is flagged as a poor
  fit rather than treated as failure.
- **FFT View** — reveals a frequency-domain plot in the bottom ~⅓ of the window
  (waveform compressed into the top ~⅔). Computes the one-sided spectrum of one
  channel live during Run. Controls:
  - **Channel** (one signal at a time)
  - **Quantity**: Amplitude (V) or ASD (V/√Hz)
  - **Scale**: Linear or dB
  - **Window**: Hann / Hamming / Blackman / Rectangular
  - **Frequency range** Min/Max (MHz) + *Full (Nyquist)*
  - *Auto Y* — fit the y-axis to the data in the visible frequency range

  The spectrum keeps all FFT bins; the readout reports fs, Nyquist, bin spacing
  df = fs/N, and the window's equivalent noise bandwidth (ENBW).
- **VRS Alignment** — align a VRS doublet to a bare-cavity resonance. You step the
  cavity frequency *externally*; each triggered shot must hold two TTL-gated
  windows on the signal channel — window 1 a double Lorentzian (the doublet),
  window 2 a single Lorentzian (bare cavity). The asymmetry = (doublet center −
  single center), scaled to kHz by the scan rate, is plotted vs. cavity frequency
  on the bottom pane; a weighted line fit reports the zero-crossing (the cavity
  frequency to move to). Controls:
  - **Channels**: Signal + TTL
  - **Time window**: start/stop (ms) to crop each capture (`stop ≤ start` = whole
    capture); cropping never reconfigures the scope
  - **TTL gating**: threshold (V), min pulse width (ms)
  - **Scan scaling**: scan range (MHz) + scan time (ms) → the time→kHz factor
  - **Cavity sweep**: start (MHz), step (MHz), num steps, min R²
  - **Start Analysis** / **Reset**, with a live Total-time readout

  Set the acquisition **Mode to Triggered** first — Start arms a continuous
  triggered run and treats every *successful* shot as the next sweep point
  (advancing once per trigger as you retune the cavity). Failed shots (wrong TTL
  count, short window, bad/low-R² fit) are reported and do **not** advance, so you
  can retrigger at the same setting.

### Display point cap

Each waveform trace is drawn at ≤ 5000 points (stride decimation) for fast frame
updates. This affects the **display only** — the stored capture stays
full-resolution, and analysis (fits, FFT) and *Save full* use the complete data.
The cap does not apply to the FFT spectrum.

---

## Using the analysis from a notebook

`analysis.py` has no Qt dependency, so the math behind the GUI is directly
importable:

```python
import sys
sys.path.insert(0, "Cscope control driver")   # vendor modules use flat imports

from analysis import fit_lorentzian, compute_spectrum

res = fit_lorentzian(t, channels[2])
if res["success"]:
    print(res["params"]["fwhm"], res["r2"])

spec = compute_spectrum(t, channels[0], window="hann", scaling="asd")
# spec["f"], spec["mag"] (V/√Hz), spec["df"], spec["enbw"], spec["nyquist"]
```

The control layer is equally usable headless:

```python
from controller import ScopeController
c = ScopeController(simulate=True)
c.connect(); c.apply_config()
t, channels, metrics = c.acquire_once("Triggered")
```

---

## Documentation & conventions

- **Commit log:** every commit gets a `docs/commit-log/NNN-slug.md` documenting
  what changed, why, how it was verified, and notes for future work, with
  `docs/commit-log/index.md` updated. See that folder for the running history.
- **README:** keep this file current — it is updated on every push so it always
  reflects the latest state of the app.
- See `CLAUDE.md` for the full set of project conventions.

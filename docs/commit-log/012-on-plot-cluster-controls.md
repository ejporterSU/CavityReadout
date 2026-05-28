# 012 — On-plot zoom/pan/reset clusters, per-channel ViewBoxes, signal-direction pan

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-27

## What

Replaced the manual numeric spinboxes that set the time window and per-channel
voltage ranges with five button clusters embedded directly on the plot, each
driving a fully independent display per channel:

### `ButtonCluster` widget (new, in [gui.py](Cscope%20control%20driver/gui.py))
Five `QToolButton`s — pan−, zoom out, reset, zoom in, pan+ — with an
optional CSS color tint and an optional numeric readout label.
- `show_readout=False` (used by all on-plot clusters) drops the redundant
  numeric label — the axis tick scale already shows the programmed range.
- Orientation `"v"` lays buttons out vertically (`^ + R − v` top-to-bottom)
  so the pan arrows map to actual screen direction; `"h"` lays them
  horizontally (`< − R + >`).
- Translucent white button backgrounds so the cluster reads against waveform
  data.

### Plot layout
- **One ViewBox per channel** (`self._vb[0..3]`), all stacked in the same
  on-screen rectangle and X-linked so the time axis stays unified. This is
  the key fix that lets each channel have a fully independent Y display:
  zooming A no longer rescales B (and zooming C no longer rescales D), the
  way real multi-trace scopes behave.
- The left axis re-links between A's and B's ViewBoxes (and the right
  between C's and D's) every time the user presses that channel's cluster,
  via `_tint_axis(ch)`. That method also:
  - colors the axis the channel's pen color
  - relabels it `Voltage <name>` (e.g. "Voltage A" → "Voltage B")
  - calls `axis.linkedViewChanged(view)` explicitly after `linkToView`,
    because pyqtgraph's `linkToView` only wires signals — it doesn't push
    the freshly-linked view's current range. Without this manual sync the
    axis tick labels stayed on the previous channel's range until the next
    button click.
- `HoverAxis` lost its class-level `NORMAL` constant in favor of a
  per-instance `_normal_color` (set via `set_normal_color()`), so hover-leave
  returns the axis to its channel color rather than the old gray.
- A and B render against the **left** axis, C and D against the **right**.

### On-plot cluster placement
- **A (red)** → top-left of plot, **B (blue)** → bottom-left (vertical
  columns hugging the left axis).
- **C (green)** → top-right, **D (orange)** → bottom-right.
- **Time** → centered horizontally in a row directly under the bottom axis.
- Channel clusters are children of `self.plot`; a `eventFilter` on the plot
  widget re-runs `_reposition_overlays()` on every `QEvent.Resize` to keep
  them pinned with a 6-px inward pad. The time cluster lives in its own
  horizontal layout sitting between the plot widget and the splitter's
  second pane.
- The plot + time-row are wrapped in one `QWidget` and slotted into the
  existing `plot_splitter` in place of the bare plot.

### Pan-direction convention
Pan signs are flipped at the wiring layer so the button labels describe
what the **signal** does on screen, not what the range does:
- `v` → range shifts up (signal appears lower)
- `^` → range shifts down (signal appears higher)
- `<` → time window slides later (signal appears earlier in the window)
- `>` → time window slides earlier (signal appears later)

Tooltips updated to match ("Pan signal down by 1/4 span", etc.). The
underlying `_pan_bounds()` math is unchanged.

### Side panel slimming
- "Time base" group is now just `Rate` + sample-count label `N`.
- "Channels" rows are now `On | Ch | Cpl` — no more `Min`/`Max` spinboxes or
  per-row cluster column.

### Other fixes / changes
- `LorentzianFitMode` already calls `host._viewbox_for(ch)`, which now
  returns the per-channel ViewBox, so the dashed fit overlay attaches to the
  correct channel's coordinate system without any change to the mode.
- `autoscale_y` now fits each enabled channel's own ViewBox independently
  (one pass per channel instead of one pass per axis side).
- Snapshot of the startup `ScopeConfig` is captured in `ScopeWindow.__init__`
  (`self._config_defaults`) so each cluster's Reset (R) button restores its
  programmed value to whatever it was on launch.
- Endpoints silently clamp at ±100 V (and at ≥ 2 samples for the time
  window); no error dialogs.

### MockScope rewrite (in [controller.py](Cscope%20control%20driver/controller.py))
The old simulator scaled each channel's signal amplitude as a fraction of
that channel's programmed range, which made zoom look like a no-op (the
amplitude shrank to match the new VB range, leaving the curve unchanged
visually). Switched to **absolute-amplitude** signals matching the
heterodyne cavity-readout use case:
- **A, B:** ±1 V sine I/Q pair at 10 kHz (B lags A by 90°). 10 kHz gives
  ~100 samples/cycle at the default 1 MHz sampling rate so the waveforms
  display cleanly out of the box.
- **C:** Train of Lorentzian peaks, +1 V above a 0 V baseline, 200 µs
  FWHM, repeating every 1 ms; phase-folded so peaks land at integer
  multiples of the period (one peak centered in the default ±500 µs
  window).
- **D:** 0/+2 V TTL square at 1 kHz, kept inside the default ±2.5 V range
  so it isn't railed.

Each channel still gets `np.clip`'d to its programmed `[lo, hi]` so
hardware-style railing demos correctly: tightening A's range below ±1 V
visibly clips the sine at the rails. Noise is now a flat 20 mV RMS
Gaussian, also absolute (not range-relative).

## Why

The original spinbox controls forced the user to type voltage numbers
mid-experiment. The button clusters give single-click zoom/pan with a
consistent 1.5× / ¼-span step. Moving them onto the plot at the matching
axis corners removes the long horizontal eye-jump between data and
controls. Per-channel ViewBoxes were necessary because the user explicitly
wanted A and B (and C and D) to *not* fight each other for an axis —
each channel should render at its own programmed scale.

The pan direction had to be flipped to match the user's mental model:
pressing `v` should make the trace look lower, not the range.

The MockScope rewrite was the original trigger for noticing the
zoom-does-nothing problem in `--simulate`. Absolute amplitudes were the
right move regardless of the rest of the feature.

## Verification

Headless harnesses (Qt offscreen) at each iteration confirmed:

- All 4 ViewBoxes start at the programmed ±2.5 V; left axis = red "Voltage
  A", right axis = green "Voltage C".
- Pressing A's `+` shrinks `_vb[0]` by 1/1.5 around its center; `_vb[1]`
  (B) **stays at its previous range** (the independence requirement).
- Pressing B switches the left axis: tick labels jump to B's range on the
  first click (the `linkedViewChanged` push), label flips to "Voltage B",
  color turns blue, A's VB is left untouched.
- Same dance on the right between C and D.
- Channel clusters report `parent() is self.plot`, land at the four corners
  with 6 px padding, and are 24×122 px tall vertical columns; time cluster
  is 132×22 px horizontal.
- Inverted pan: A's `v` shifts `cfg.ranges[0]` from `(-2.5, 2.5)` →
  `(-1.25, 3.75)` (range up → signal appears down); time `<` slides the
  window later.
- All 4 ViewBoxes share the same on-screen rect (within 1.5 px after
  layout settles); X-axis pan moves all of them in lockstep.
- MockScope sanity: ChA has ~20 zero crossings per default 1 ms window at
  10 kHz; A and B at ±1.06 V (noise floor visible) with B sample-shifted
  by a quarter cycle relative to A; C produces exactly 3 peaks across a
  3 ms window with fitted FWHM = 199.7 µs (R² = 0.9954);
  D rails 0/+2 V. Tightening A's range below ±1 V clips A at the rails
  while leaving its actual data amplitude untouched (the zoom-is-real
  guarantee).
- Lorentzian Fit mode with channel C selected: dashed fit overlay
  attaches to `_vb[2]` so it renders against the right-axis scale.

Live launch (`py run_scope.py --simulate`) clean across multiple iterations.

## Notes for future work

- Mouse drag on the data area still affects the topmost (main) ViewBox
  only — `_vb[0]` (A). For inspection that's fine; if the user wants
  Y-drag to follow the "last-pressed channel" or to be disabled entirely,
  that's a one-line `setMouseEnabled(y=False)` toggle.
- Axis label text stays neutral; only the tick numbers + tick marks
  carry the channel color. If the user wants the entire "Voltage A"
  label to also follow the channel color, pass `color=...` to
  `setLabel(...)` in `_tint_axis`.
- 10 kHz tones at the default 1 MHz sampling rate are well above
  Nyquist; if the user wants to demo Nyquist aliasing later, bumping
  `f_sine` in `MockScope.get_single_acquisition` is enough.
- If the user wants the time cluster vertical too (e.g., parked next to
  an axis), set `orientation="v"` on its construction in
  `_build_plot_overlays`. The button-order math already handles both.
- A keyboard-shortcut layer for the cluster buttons would be a small
  addition to `ScopeWindow`.

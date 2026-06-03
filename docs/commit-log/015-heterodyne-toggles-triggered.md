# 015 — Heterodyne viewer: demod toggles, summed phase, triggered Run/Single

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-06-03

## What

Two follow-ups to the heterodyne viewer (commit 014), all in
[heterodyne_viewer.py](../../Cscope%20control%20driver/heterodyne_viewer.py).

### Demod pane toggles + summed phase
- The magnitude and phase results moved from a shared `GraphicsLayoutWidget` into
  two separate `PlotWidget`s stacked in a container, so each can carry its own row
  of show/hide **toggle buttons** (colored to match their traces; filled when on).
- **Magnitude pane:** two toggles, one per beat tone (`f_B − f_C`, `f_B + f_C`).
- **Phase pane:** three toggles — each tone plus their **Sum**. The new
  `phase_sum_curve` plots `phase(f_B−f_C) + phase(f_B+f_C)`; it is **off by
  default** and, when enabled, widens the phase y-range from ±π to ±2π (the sum
  spans twice the single-phase range), snapping back when disabled.
- The old per-plot legend was dropped — the colored toggle buttons now serve as
  the legend. Both plots stay X-linked to channel A (navigator zoom still drives
  them). Helpers: `_make_toggle`, `_on_phase_sum_toggled`; `_compute_demod` now
  also sets the summed-phase trace (and clears it on the no-tone path).

### Run/Single never auto-trigger
- `DemodAcquisitionWorker` gained a `mode` argument that it passes to
  `acquire_once(mode)` (previously it used the controller default `acq_mode`,
  which was `"Auto"` — so **Single force-acquired instead of waiting**).
- Both **Single** and **Run** now acquire in single-shot `"Single"` mode, which
  waits for a real trigger. *Single* takes one shot; *Run* re-arms another
  single-shot after each frame finishes analyzing (the existing frame-drop gate),
  so triggered shots come in one at a time and triggers during analysis are
  dropped. The viewer never auto-triggers.
- In a re-arming *Run*, a per-acquire timeout (no trigger yet) is no longer
  reported as a failure: it shows **"Waiting for trigger…"** and arms the next
  single-shot. `default_config()` `acq_mode` is now `"Single"` to match.

## Why

Toggling individual tones makes it possible to look at one sideband at a time, and
the summed phase is a quantity the lab wants directly. On the acquisition side,
heterodyne shots are TTL-gated, so a capture must align to a real trigger; the old
`"Auto"` mode force-acquired (Single fired immediately; Run free-ran), which is not
what a triggered, shot-by-shot measurement needs. Re-arming a single-shot per
analyzed frame matches the operator's mental model ("watch the shots come in") and,
with the gate, keeps the heavy demod from overrunning the acquisition.

## Verification

No hardware. Headless harnesses (`QT_QPA_PLATFORM=offscreen`), each run then deleted:

- **Toggles:** five checkable buttons present (2 magnitude + 2 phase + Sum);
  defaults = tones visible, Sum hidden; hiding a tone removes its curve while the
  other stays; the Sum trace equals `phase0 + phase1` (compared on raw `.yData`,
  since `getData()` is peak-decimated); phase y-range goes ±π → ±2π → ±π as Sum is
  toggled on/off.
- **Trigger modes:** *Single* calls `acquire_once("Single")`; *Run* uses `"Single"`
  for **every** acquisition (never `"Auto"`), re-arms (3 acquisitions / 2 analyzed
  frames over the test window), and stays ≤ 1 acquisition ahead of analysis (gate
  intact); Stop halts cleanly.

## Notes for future work

- Each armed single waits up to the acquire timeout (10 s); with sparser triggers
  you'll see brief "Waiting for trigger…" cycles, and a trigger landing in the
  ~20 ms re-arm gap can be missed. A longer/!configurable trigger-wait timeout would
  help, at the cost of a less responsive **Stop** (it can't interrupt a blocking
  acquire — `Stop` may take up to the timeout to finalize).
- The demod still runs on the GUI thread (see 014's note); moving it into the
  worker remains the path to a responsive UI at higher shot rates.
- Sum is the raw arithmetic sum of two wrapped phases (range ±2π); if a wrapped
  combined phase (±π) is wanted instead, change `phase0 + phase1` to
  `np.angle(np.exp(1j*(phase0+phase1)))` in `_compute_demod`.

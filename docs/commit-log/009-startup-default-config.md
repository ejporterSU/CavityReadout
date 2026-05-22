# 009 — New startup defaults (±2.5 V DC, 1 MHz, ±500 µs)

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-22

## What
Changed the app's power-on configuration (`ScopeConfig` defaults), with `MockScope`'s
mirrored fallbacks kept in sync.

- `Cscope control driver/controller.py`:
  - `ScopeConfig`: `sampling_rate_hz` 100 MHz → **1 MHz**; `stop_time_s` 6.5 ms →
    **0.5 ms** (`start_time_s` was already −0.5 ms, giving a **±500 µs** window);
    `ranges` → **(−2.5, 2.5) V on all four channels**; `couplings` → **DC on all four**.
  - `MockScope.__init__`: same start/stop/rate/ranges values so the simulate-mode
    fallbacks match (they're overwritten on connect/apply anyway, kept identical by
    convention).

These flow into the GUI automatically via `_sync_controls_to_config`, so the panel
shows them on launch. With the new window, N = 1 ms × 1 MHz = **1000 samples**.

## Why
User's requested defaults for routine startup: every channel ±2.5 V, DC-coupled,
1 MHz sampling, ±500 µs time range.

## Verification
Headless (`QT_QPA_PLATFORM=offscreen`, simulate): on launch the rate combo read
"1 MHz", start/stop spinboxes −0.5/+0.5 ms, N = 1000, and all four channels
min/max = −2.5/+2.5 with coupling DC.

## Notes for future work
- 1 MHz is in the GUI's `_rate_values` list, so the combo maps exactly; if a non-listed
  rate is ever set as a default, `_sync_controls_to_config` snaps to the nearest entry.

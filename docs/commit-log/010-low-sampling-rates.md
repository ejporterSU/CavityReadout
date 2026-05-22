# 010 — Add 400/200/100 kHz sampling-rate options

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-22

## What
- `Cscope control driver/gui.py`: appended `400e3, 200e3, 100e3` to the time-base
  rate combo's `_rate_values`. They render as "400 kHz", "200 kHz", "100 kHz" via the
  existing `fmt_hz` (sub-MHz → kHz).

## Why
User wanted lower sampling rates available. Nothing in the driver imposes a lower
bound: `cscope_class.update_time_axis` derives `NumSamples = (stop-start)·rate`, and
the only documented constraints are the *max* rate (400 MS/s) and a 4M-sample cap, so
lower rates are valid — they simply yield fewer samples per window.

## Verification
Headless (`QT_QPA_PLATFORM=offscreen`, simulate): the combo lists 400/200/100 kHz
alongside the existing rates; startup default stays "1 MHz"; selecting "100 kHz" over
the default ±500 µs window gives N = 100 samples as expected.

## Notes for future work
- These have only been exercised in simulate. On real hardware, confirm the scope
  decimates/clocks correctly at these rates and that the resulting low N still
  triggers as expected.

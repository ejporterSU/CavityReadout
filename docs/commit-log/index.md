# Commit log

One file per commit, documenting *what changed and why*, so the history can be
reviewed at a glance for future work. Files are named `NNN-<shorthash>-<slug>.md`
in commit order (oldest first). The git message has the canonical record; these
notes add intent, context, and follow-ups that don't belong in a commit message.

| # | Commit | Date | Summary |
|---|--------|------|---------|
| 001 | [0e3e517](001-0e3e517-initial-commit.md) | 2026-05-21 | Initial commit: Cleverscope control driver + vendor files |
| 002 | [5d28625](002-5d28625-pyqtgraph-readout-app.md) | 2026-05-21 | Simplified PyQtGraph readout app (controller + GUI + launcher) |
| 003 | [setup](003-commit-log-setup.md) | 2026-05-21 | Set up the commit-log documentation folder |
| 004 | [claude-md](004-claude-md-project-memory.md) | 2026-05-21 | Add CLAUDE.md for cross-machine project memory |
| 005 | [analysis-modes](005-analysis-modes-lorentzian.md) | 2026-05-21 | Analysis-mode framework + Lorentzian fit mode |
| 006 | [hw-fixes](006-hardware-connect-fixes.md) | 2026-05-22 | Hardware bring-up fixes: NumPy 2.0 fromstring, absolute DLL path, disconnect hang + IsConnected |
| 007 | [fft-view](007-fft-view-mode.md) | 2026-05-22 | FFT View mode: single-channel spectrum analyzer (amplitude/ASD, linear/dB, windowing) in a bottom split pane |
| 008 | [display-cap](008-display-decimation-save-buttons.md) | 2026-05-22 | Waveform display capped at 5000 pts (display-only); Free View split into Save display / Save full buttons |
| 009 | [defaults](009-startup-default-config.md) | 2026-05-22 | New startup defaults: ±2.5 V DC on all channels, 1 MHz sampling, ±500 µs window |
| 010 | [low-rates](010-low-sampling-rates.md) | 2026-05-22 | Add 400/200/100 kHz options to the time-base rate selector |
| 011 | [readme](011-readme-and-push-rule.md) | 2026-05-22 | Add top-level README; convention to update it on every push |
| 012 | [on-plot-clusters](012-on-plot-cluster-controls.md) | 2026-05-27 | On-plot zoom/pan/reset cluster buttons replacing the side-panel spinboxes; per-channel ViewBoxes so A/B/C/D each render at their own range; left axis re-links between A/B and right between C/D with color + label following the last-pressed channel; signal-direction pan; MockScope rewrite to absolute-amplitude 10 kHz I/Q + Lorentzian train + TTL |
| 013 | [vrs-alignment](013-vrs-cavity-alignment-mode.md) | 2026-06-01 | VRS–cavity alignment sweep mode: per-shot double/single Lorentzian fit across two TTL windows, asymmetry (kHz) vs externally-stepped cavity frequency, weighted line fit + zero-crossing; `single_lorentzian`/`double_lorentzian`/`segment_ttl`/`fit_window_asymmetry` added to analysis.py |
| 014 | [heterodyne-viewer](014-heterodyne-viewer.md) | 2026-06-03 | New standalone heterodyne viewer (`run_heterodyne.py`/`heterodyne_viewer.py`): all-channel display, D full-window navigator region driving the A/B/C + demod views, channel-A magnitude band; IQ-demodulates A against the B·C reference at `f_B ± f_C` (mag `4(I²+Q²)` + phase); two-tone Lorentzian simulation; frame-drop acquisition worker; `envelope`/`dominant_frequency`/`demodulate_beatnote` added to analysis.py |

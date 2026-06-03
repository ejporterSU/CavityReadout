"""Bare-bones heterodyne signal viewer.

A small, standalone PyQtGraph app for *looking at* the four raw Cleverscope
channels of a heterodyne measurement — separate from the full readout in
`gui.py`. There is no heterodyne processing yet: each channel is simply drawn in
its own stacked plot. This is the starting point for a heterodyne *processing*
viewer, so it is deliberately minimal and easy to extend.

Channel roles on this rig (fixed):
    A  heterodyne beat signal
    B  RF signal 1   (later mixed -> mixer signal)
    C  RF signal 2   (later mixed -> mixer signal)
    D  TTL gate

All four channels are always read. You enter the measurement duration; the
capture window is that duration padded by +/-100 us (`GUARD_S`) so the TTL edges
sit inside a guard band. Per-channel vertical scale is a +/- magnitude chosen
from a dropdown; sampling rate is a dropdown too.

Reuses the hardware-agnostic control layer (`controller.ScopeController` /
`ScopeConfig`); only the simulate path differs, swapping in `HeterodyneMockScope`
for signals tuned to this rig. Acquisition runs on its own thread
(`DemodAcquisitionWorker`) that drops frames while the GUI is still analyzing, so
the heavy demod can't back up the queue or time the scope out.

Launch via run_heterodyne.py (handles sys.path / cwd / the DLL), or directly:
    python heterodyne_viewer.py --simulate
"""

import sys
import threading

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from controller import ScopeController, ScopeConfig, CH_NAMES, CH_COLORS
from analysis import envelope, dominant_frequency, demodulate_beatnote


# Colors / labels for the two demodulated tones (lower / upper sideband).
DEMOD_COLORS = ["#9467bd", "#17becf"]            # purple, teal
DEMOD_LABELS = ["f_B − f_C", "f_B + f_C"]


# Per-channel role, parallel to CH_NAMES = ["A", "B", "C", "D"].
CHANNEL_ROLES = ["Heterodyne", "RF 1 (mix)", "RF 2 (mix)", "TTL"]

# Vertical-scale choices: (magnitude_volts, label). The range becomes +/- magnitude.
SCALE_OPTIONS = [
    (0.01, "10 mV"), (0.02, "20 mV"), (0.05, "50 mV"),
    (0.1, "100 mV"), (0.2, "200 mV"), (0.5, "500 mV"),
    (1.0, "1 V"), (2.0, "2 V"), (5.0, "5 V"),
]

# Sampling-rate choices (Hz). 50 MHz default => ~12 samples/cycle at 4 MHz.
# 400 MHz is the scope's max.
RATE_OPTIONS = [400e6, 200e6, 100e6, 50e6, 20e6, 10e6, 5e6, 1e6]

GUARD_S = 100e-6     # padding added on each side of the measurement window
TTL_HIGH_V = 3.3     # simulated TTL logic-high level


def _fmt_hz(hz):
    for div, unit in [(1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")]:
        if abs(hz) >= div:
            return f"{hz/div:g} {unit}"
    return f"{hz:g} Hz"


def default_config():
    """Startup config for the viewer: 3 ms measurement (+/-100 us guard) at
    50 MHz, A/B/C AC-coupled at +/-1 V, D (TTL) DC-coupled at +/-5 V, trigger on
    D rising at t=0. All four channels enabled."""
    return ScopeConfig(
        sampling_rate_hz=50e6,
        start_time_s=-GUARD_S,
        stop_time_s=3e-3 + GUARD_S,
        ranges=[(-1.0, 1.0), (-1.0, 1.0), (-1.0, 1.0), (-5.0, 5.0)],
        couplings=["AC", "AC", "AC", "DC"],
        enabled=[True, True, True, True],
        trigger_channel="D",
        trigger_level_v=1.0,
        trigger_slope="Rising",
        acq_mode="Auto",
    )


class HeterodyneMockScope:
    """Synthetic stand-in for `CScope`, tuned for the heterodyne rig so simulate
    mode runs with no DLL or hardware. Mirrors the subset of the CScope API that
    `ScopeController` calls.

    Signals are at absolute amplitudes; the channel range only clips (rails)
    them, the way real hardware does:
        A: heterodyne beat = two tones at F_B-F_C (3.5 MHz) and F_B+F_C (4.5 MHz),
           each with its own Lorentzian amplitude envelope, the two offset by
           ~1 HWHM (mimics two slightly misaligned cavity resonances).
        B: F_B = 4.0 MHz sine    (RF 1)
        C: F_C = 0.5 MHz sine    (RF 2)
        D: 0 / 3.3 V TTL, high across the measurement window
           [start+GUARD_S, stop-GUARD_S] so its edges fall inside the guard band.

    A's two tones sit at F_B +/- F_C, so multiplying B*C reproduces them as the
    demodulation reference (see the viewer's demod panel).
    """

    MAX_SAMPLES = 200_000   # cap synthetic frame size for a smooth live loop
    F_B, F_C = 4.0e6, 0.5e6
    AMP = 0.5               # per-tone sine amplitude (V)

    def __init__(self):
        self.start = -GUARD_S
        self.stop = 3e-3 + GUARD_S
        self.rate = 50e6
        self.ranges = [(-1.0, 1.0), (-1.0, 1.0), (-1.0, 1.0), (-5.0, 5.0)]
        self._connected = False
        self._rng = np.random.default_rng()

    # --- mirror the CScope API the controller uses ---
    def connect(self, **kwargs):
        self.start = kwargs.get("start_time_s", self.start)
        self.stop = kwargs.get("stop_time_s", self.stop)
        self.rate = kwargs.get("sampling_rate_hz", self.rate)
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def IsConnected(self):
        return self._connected

    def update_time_axis(self, start, stop, sampling_rate):
        self.start, self.stop, self.rate = start, stop, sampling_rate
        return True

    def update_trigger(self, trig_ch, TriggerLevel=0.5, TriggerType="Rising"):
        return True

    def set_ch_range(self, ChannelIndex, MinVolts, MaxVolts):
        self.ranges[ChannelIndex] = (MinVolts, MaxVolts)
        return True

    def set_ch_coupling(self, ChannelIndex, coupling):
        return True

    def get_single_acquisition(self, acq_type=None, timeout=10.0):
        duration = self.stop - self.start
        n_full = max(2, int(duration * self.rate))
        n = min(n_full, self.MAX_SAMPLES)
        t = np.linspace(self.start, self.stop, n)

        # Channel A = two heterodyne tones at F_B-/+F_C, each with its own
        # Lorentzian amplitude envelope across the measurement window (mimics two
        # cavity resonances). The two envelopes are offset by ~1 HWHM, so the
        # recovered magnitudes peak at slightly different times. FWHM ~ 1/4 dur.
        meas_dur = self.stop - self.start - 2 * GUARD_S
        t0 = 0.5 * (self.start + self.stop)
        hwhm = max(meas_dur / 8.0, 1e-12)          # FWHM = meas_dur/4 -> HWHM = /8
        lor = lambda center: hwhm**2 / ((t - center)**2 + hwhm**2)
        f_lo, f_hi = self.F_B - self.F_C, self.F_B + self.F_C
        a_sig = self.AMP * (lor(t0 - hwhm / 2.0) * np.sin(2 * np.pi * f_lo * t)
                            + lor(t0 + hwhm / 2.0) * np.sin(2 * np.pi * f_hi * t))
        b_sig = self.AMP * np.sin(2 * np.pi * self.F_B * t)
        c_sig = self.AMP * np.sin(2 * np.pi * self.F_C * t)
        # TTL high across the guard-padded interior = the measurement window.
        high = (t >= self.start + GUARD_S) & (t <= self.stop - GUARD_S)
        d_sig = np.where(high, TTL_HIGH_V, 0.0)

        channels = []
        for i, sig in enumerate([a_sig, b_sig, c_sig, d_sig]):
            noise = self._rng.normal(0.0, 0.01, size=n)   # ~10 mV noise floor
            lo, hi = self.ranges[i]
            channels.append(np.clip(sig + noise, lo, hi))
        return [t, tuple(channels)]


class HeterodyneController(ScopeController):
    """`ScopeController` whose simulate path uses `HeterodyneMockScope` instead
    of the default `MockScope`, so synthetic signals match the heterodyne rig.
    The real-hardware path is inherited unchanged."""

    def connect(self):
        if not self.simulate:
            return super().connect()
        cfg = self.config
        self._scope = HeterodyneMockScope()
        self._scope.connect(
            start_time_s=cfg.start_time_s,
            stop_time_s=cfg.stop_time_s,
            sampling_rate_hz=cfg.sampling_rate_hz,
        )
        self._dirty = True
        return self.connected


class DemodAcquisitionWorker(QtCore.QThread):
    """Acquisition loop that drops frames while the GUI is busy.

    Like the readout app's worker it acquires off the GUI thread, but in
    continuous mode it does not acquire the next frame until the GUI has finished
    drawing *and* demodulating the current one (signalled via `notify_processed`).
    Triggers that arrive during analysis are therefore never acquired — they are
    dropped rather than queued. This keeps the heavy per-frame demod from backing
    up the event queue and, on real hardware, from starving the acquisition's
    own wait loop until it times out.
    """

    frameReady = QtCore.Signal(object)   # (t, channels, metrics)
    failed = QtCore.Signal(str)

    def __init__(self, controller, continuous, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._continuous = continuous
        self._running = True
        self._processed = threading.Event()
        self._processed.set()

    def stop(self):
        self._running = False
        self._processed.set()   # release the loop if it's waiting on the GUI

    def notify_processed(self):
        """Called by the GUI once it has finished handling the emitted frame."""
        self._processed.set()

    def run(self):
        while self._running:
            if self._controller.needs_apply():
                self._controller.apply_config()
            t, channels, metrics = self._controller.acquire_once()
            if not self._running:
                return
            if t is None:
                self.failed.emit("Acquisition failed or timed out.")
                if not self._continuous:
                    return
                self.msleep(20)
                continue
            if not self._continuous:
                self.frameReady.emit((t, channels, metrics))
                return
            # Continuous: hand off the frame, then wait for the GUI to finish
            # analyzing it before acquiring again (intervening triggers dropped).
            self._processed.clear()
            self.frameReady.emit((t, channels, metrics))
            self._processed.wait()


class HeterodyneViewer(QtWidgets.QMainWindow):
    """Minimal four-channel viewer: a small control column on the left, four
    stacked X-linked plots (A-D) on the right. `on_frame` is the single draw
    path (one curve per channel)."""

    def __init__(self, simulate=False):
        super().__init__()
        self.setWindowTitle("Heterodyne Viewer" + (" [SIMULATION]" if simulate else ""))
        self.resize(1500, 780)

        self.controller = HeterodyneController(simulate=simulate, config=default_config())
        self.worker = None
        self._continuous = False
        self._loading = False
        self._syncing = False        # guards the region <-> A-view feedback loop
        self._last_window = None     # (start, stop) the navigator was last sized to

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.addWidget(self._build_controls(), 0)
        # Raw channels (left) + demod results (right) in a resizable splitter.
        # _build_demod_plots links to self.plots[0], so build the channels first.
        plots_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        plots_split.addWidget(self._build_plots())
        plots_split.addWidget(self._build_demod_plots())
        plots_split.setSizes([760, 540])
        layout.addWidget(plots_split, 1)

        self._sync_controls_to_config()
        self._set_running_state(False)

    # ---------- UI construction ----------
    def _build_controls(self):
        panel = QtWidgets.QWidget()
        panel.setFixedWidth(260)
        v = QtWidgets.QVBoxLayout(panel)
        v.setSpacing(6)
        v.setContentsMargins(6, 6, 6, 6)

        # connection
        conn = QtWidgets.QGroupBox("Connection")
        cg = QtWidgets.QGridLayout(conn)
        self.serial_edit = QtWidgets.QLineEdit(self.controller.config.serial_number)
        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connect)
        self.status_lbl = QtWidgets.QLabel("Disconnected")
        self.status_lbl.setWordWrap(True)
        cg.addWidget(QtWidgets.QLabel("Serial"), 0, 0)
        cg.addWidget(self.serial_edit, 0, 1)
        cg.addWidget(self.connect_btn, 1, 0, 1, 2)
        cg.addWidget(self.status_lbl, 2, 0, 1, 2)
        v.addWidget(conn)

        # measurement window (duration -> start/stop +/- guard)
        meas = QtWidgets.QGroupBox("Measurement")
        mg = QtWidgets.QGridLayout(meas)
        self.duration_spin = QtWidgets.QDoubleSpinBox()
        self.duration_spin.setRange(0.001, 1000.0)   # ms
        self.duration_spin.setDecimals(3)
        self.duration_spin.setSuffix(" ms")
        self.duration_spin.setSingleStep(0.1)
        self.duration_spin.valueChanged.connect(self._on_config_changed)
        self.window_lbl = QtWidgets.QLabel("")
        self.window_lbl.setWordWrap(True)
        mg.addWidget(QtWidgets.QLabel("Duration"), 0, 0)
        mg.addWidget(self.duration_spin, 0, 1)
        mg.addWidget(self.window_lbl, 1, 0, 1, 2)
        v.addWidget(meas)

        # sampling rate
        rate = QtWidgets.QGroupBox("Sampling")
        rg = QtWidgets.QGridLayout(rate)
        self.rate_combo = QtWidgets.QComboBox()
        self.rate_combo.addItems([_fmt_hz(r) for r in RATE_OPTIONS])
        self.rate_combo.currentIndexChanged.connect(self._on_config_changed)
        self.nsamp_lbl = QtWidgets.QLabel("")
        rg.addWidget(QtWidgets.QLabel("Rate"), 0, 0)
        rg.addWidget(self.rate_combo, 0, 1)
        rg.addWidget(self.nsamp_lbl, 1, 0, 1, 2)
        v.addWidget(rate)

        # per-channel vertical scale (+/- magnitude)
        scale = QtWidgets.QGroupBox("Scale (±)")
        sg = QtWidgets.QGridLayout(scale)
        self.scale_combos = []
        for i, name in enumerate(CH_NAMES):
            lbl = QtWidgets.QLabel(f"{name} — {CHANNEL_ROLES[i]}")
            lbl.setStyleSheet(f"color: {CH_COLORS[i]}; font-weight: bold;")
            combo = QtWidgets.QComboBox()
            combo.addItems([s[1] for s in SCALE_OPTIONS])
            combo.currentIndexChanged.connect(self._on_config_changed)
            sg.addWidget(lbl, i, 0)
            sg.addWidget(combo, i, 1)
            self.scale_combos.append(combo)
        v.addWidget(scale)

        # demod filter parameters (post-processing only; do not re-acquire)
        demod = QtWidgets.QGroupBox("Demod")
        dgg = QtWidgets.QGridLayout(demod)
        self.bw_spin = QtWidgets.QDoubleSpinBox()
        self.bw_spin.setRange(1.0, 100000.0)
        self.bw_spin.setDecimals(0)
        self.bw_spin.setSuffix(" kHz")
        self.bw_spin.setValue(500)
        self.bw_spin.valueChanged.connect(self._redraw_demod)
        self.lp_spin = QtWidgets.QDoubleSpinBox()
        self.lp_spin.setRange(1.0, 100000.0)
        self.lp_spin.setDecimals(0)
        self.lp_spin.setSuffix(" kHz")
        self.lp_spin.setValue(100)
        self.lp_spin.valueChanged.connect(self._redraw_demod)
        self.demod_lbl = QtWidgets.QLabel("")
        self.demod_lbl.setWordWrap(True)
        dgg.addWidget(QtWidgets.QLabel("Bandpass BW"), 0, 0)
        dgg.addWidget(self.bw_spin, 0, 1)
        dgg.addWidget(QtWidgets.QLabel("Lowpass cut"), 1, 0)
        dgg.addWidget(self.lp_spin, 1, 1)
        dgg.addWidget(self.demod_lbl, 2, 0, 1, 2)
        v.addWidget(demod)

        # run controls
        run = QtWidgets.QGroupBox("Run")
        rng = QtWidgets.QGridLayout(run)
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self.start_continuous)
        self.single_btn = QtWidgets.QPushButton("Single")
        self.single_btn.clicked.connect(self.start_single)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_acquisition)
        rng.addWidget(self.run_btn, 0, 0)
        rng.addWidget(self.single_btn, 0, 1)
        rng.addWidget(self.stop_btn, 0, 2)
        v.addWidget(run)

        v.addStretch(1)
        return panel

    def _build_plots(self):
        pg.setConfigOptions(antialias=True)
        glw = pg.GraphicsLayoutWidget()
        glw.setBackground("w")
        self.plots = []
        self.curves = []
        for i, name in enumerate(CH_NAMES):
            p = glw.addPlot(row=i, col=0)
            p.showGrid(x=True, y=True, alpha=0.3)
            p.setLabel("left", f"{name} — {CHANNEL_ROLES[i]}", units="V")
            if i == 2:        # C: bottom of the A/B/C group -> shows their (zoomed) time axis
                p.setLabel("bottom", "Time", units="s")
            elif i == 3:      # D: navigator, always the full window
                p.setLabel("bottom", "Time (full window)", units="s")
            else:             # A, B: share C's axis, hide ticks
                p.getAxis("bottom").setStyle(showValues=False)
            # A/B/C share one X range (B, C follow A); D stays independent and
            # fixed so it can act as the navigator.
            if 1 <= i <= 2:
                p.setXLink(self.plots[0])
            curve = p.plot(pen=pg.mkPen(CH_COLORS[i], width=1))
            curve.setDownsampling(auto=True)   # keep big captures cheap to draw
            curve.setClipToView(True)
            self.plots.append(p)
            self.curves.append(curve)

        # Navigator: a draggable/resizable region on D selects the time window
        # shown by A/B/C. D's own time axis stays fixed (X mouse disabled); only
        # the region moves. Region <-> A-view are kept in sync both directions.
        self.region = pg.LinearRegionItem()
        self.region.setZValue(10)
        self.plots[3].addItem(self.region)
        self.plots[3].getViewBox().setMouseEnabled(x=False)
        self.region.sigRegionChanged.connect(self._on_region_changed)
        self.plots[0].getViewBox().sigXRangeChanged.connect(self._on_view_xrange_changed)

        # Light-gray band on D showing channel A's amplitude envelope (its
        # "magnitude") across the full window — a navigation aid that previews
        # where A has signal (e.g. the simulated Lorentzian). Scaled so A's
        # full-scale magnitude maps onto D's range (see _draw_envelope).
        gray = pg.mkPen((170, 170, 170), width=1)
        self._env_hi = self.plots[3].plot(pen=gray)
        self._env_lo = self.plots[3].plot(pen=gray)
        self._env_fill = pg.FillBetweenItem(self._env_hi, self._env_lo,
                                            brush=pg.mkBrush(210, 210, 210, 90))
        self.plots[3].addItem(self._env_fill)
        for it in (self._env_hi, self._env_lo, self._env_fill):
            it.setZValue(-10)   # keep the band behind the TTL trace
        return glw

    def _build_demod_plots(self):
        """Right column: demodulated magnitude (top) and phase (bottom), each
        overlaying both tones. X-linked to channel A so they follow the navigator
        zoom exactly like the raw channels."""
        glw = pg.GraphicsLayoutWidget()
        glw.setBackground("w")

        self.mag_plot = glw.addPlot(row=0, col=0)
        self.mag_plot.showGrid(x=True, y=True, alpha=0.3)
        self.mag_plot.setLabel("left", "4 (I² + Q²)", units="V²")
        self.mag_plot.getAxis("bottom").setStyle(showValues=False)
        self.mag_plot.addLegend(offset=(-10, 10))

        self.phase_plot = glw.addPlot(row=1, col=0)
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)
        self.phase_plot.setLabel("left", "Phase atan2(Q, I)", units="rad")
        self.phase_plot.setLabel("bottom", "Time", units="s")
        self.phase_plot.setYRange(-np.pi, np.pi, padding=0.05)

        # Follow channel A's view (and thus the navigator region) in time.
        self.mag_plot.setXLink(self.plots[0])
        self.phase_plot.setXLink(self.plots[0])

        self.mag_curves = []
        self.phase_curves = []
        for k in range(2):
            pen = pg.mkPen(DEMOD_COLORS[k], width=1)
            mc = self.mag_plot.plot(pen=pen, name=DEMOD_LABELS[k])
            pc = self.phase_plot.plot(pen=pen, name=DEMOD_LABELS[k])
            for c in (mc, pc):
                c.setDownsampling(auto=True)
                c.setClipToView(True)
            self.mag_curves.append(mc)
            self.phase_curves.append(pc)
        return glw

    # ---------- config <-> widgets ----------
    def _sync_controls_to_config(self):
        cfg = self.controller.config
        self._loading = True
        self.serial_edit.setText(cfg.serial_number)
        duration_s = cfg.stop_time_s - cfg.start_time_s - 2 * GUARD_S
        self.duration_spin.setValue(max(self.duration_spin.minimum(), duration_s * 1e3))
        nearest = min(range(len(RATE_OPTIONS)),
                      key=lambda k: abs(RATE_OPTIONS[k] - cfg.sampling_rate_hz))
        self.rate_combo.setCurrentIndex(nearest)
        for i in range(4):
            mag = cfg.ranges[i][1]   # ranges are symmetric (-mag, +mag)
            idx = min(range(len(SCALE_OPTIONS)),
                      key=lambda k: abs(SCALE_OPTIONS[k][0] - mag))
            self.scale_combos[i].setCurrentIndex(idx)
        self._loading = False
        cfg = self.controller.config
        self._snap_window()
        self._last_window = (cfg.start_time_s, cfg.stop_time_s)
        self._snap_y()
        self._redraw_envelope()
        self._update_labels()

    def _read_config_from_controls(self):
        cfg = self.controller.config
        cfg.serial_number = self.serial_edit.text().strip() or cfg.serial_number
        duration_s = self.duration_spin.value() * 1e-3
        cfg.start_time_s = -GUARD_S
        cfg.stop_time_s = duration_s + GUARD_S
        cfg.sampling_rate_hz = RATE_OPTIONS[self.rate_combo.currentIndex()]
        for i in range(4):
            mag = SCALE_OPTIONS[self.scale_combos[i].currentIndex()][0]
            cfg.ranges[i] = (-mag, mag)

    def _on_config_changed(self, *args):
        if self._loading:
            return
        self._read_config_from_controls()
        self.controller.mark_dirty()
        cfg = self.controller.config
        window = (cfg.start_time_s, cfg.stop_time_s)
        if window != self._last_window:
            # window changed (new duration) -> reset D's full view + the region
            self._snap_window()
            self._last_window = window
        self._snap_y()
        self._update_labels()

    def _snap_window(self):
        """D shows the entire capture window (fixed); the navigator region spans
        it and drives the A/B/C view, which start out matching D (buffer included)."""
        cfg = self.controller.config
        full = [cfg.start_time_s, cfg.stop_time_s]
        self.plots[3].setXRange(*full, padding=0)
        self.region.setBounds(full)
        self.region.setRegion(full)   # fires _on_region_changed -> sets A/B/C X range

    def _snap_y(self):
        cfg = self.controller.config
        for i in range(4):
            self.plots[i].setYRange(*cfg.ranges[i], padding=0)

    def _draw_envelope(self, t, a):
        """Update D's gray band to channel A's amplitude envelope, scaled so A's
        full-scale magnitude maps to D's range (clipped if A rails)."""
        cfg = self.controller.config
        mag_a = cfg.ranges[0][1]
        d_top = cfg.ranges[3][1]
        disp = np.clip(envelope(a) / mag_a, 0.0, 1.0) * d_top
        self._env_hi.setData(t, disp)
        self._env_lo.setData(t, -disp)

    def _redraw_envelope(self):
        """Re-scale/redraw the band from the last capture (e.g. after a scale change)."""
        cap = self.controller.last_capture
        if cap is not None:
            self._draw_envelope(cap[0], cap[1][0])

    # ---------- heterodyne demodulation ----------
    def _compute_demod(self, t, channels):
        """Detect the B/C tones, build ref = B*C, and IQ-demodulate A at the two
        beat centers f_B ∓ f_C; update the magnitude/phase curves."""
        if len(t) < 2:
            return
        fs = 1.0 / (t[1] - t[0])
        a, b, c = channels[0], channels[1], channels[2]
        f_b = dominant_frequency(b, fs)
        f_c = dominant_frequency(c, fs)
        centers = [abs(f_b - f_c), f_b + f_c]
        self.demod_lbl.setText(
            f"f_B = {_fmt_hz(f_b)},  f_C = {_fmt_hz(f_c)}\n"
            f"centers: {_fmt_hz(centers[0])}, {_fmt_hz(centers[1])}")
        if f_b <= 0 or f_c <= 0:
            for k in range(2):
                self.mag_curves[k].setData([], [])
                self.phase_curves[k].setData([], [])
            return
        ref = b * c
        f_bw = self.bw_spin.value() * 1e3
        f_lp = self.lp_spin.value() * 1e3
        for k, fcen in enumerate(centers):
            mag, phase, _, _ = demodulate_beatnote(a, ref, fcen, fs,
                                                   f_bw=f_bw, f_lp=f_lp,
                                                   digital_mix=False)
            self.mag_curves[k].setData(t, mag)
            self.phase_curves[k].setData(t, phase)

    def _redraw_demod(self, *args):
        """Recompute demod from the last capture (e.g. after a filter-param edit)."""
        cap = self.controller.last_capture
        if cap is not None:
            self._compute_demod(cap[0], cap[1])

    # navigator-region <-> A-view sync (guarded so the two don't ping-pong)
    def _on_region_changed(self, *args):
        if self._syncing:
            return
        self._syncing = True
        try:
            lo, hi = self.region.getRegion()
            self.plots[0].setXRange(lo, hi, padding=0)
        finally:
            self._syncing = False

    def _on_view_xrange_changed(self, *args):
        if self._syncing:
            return
        self._syncing = True
        try:
            self.region.setRegion(self.plots[0].getViewBox().viewRange()[0])
        finally:
            self._syncing = False

    def _update_labels(self):
        cfg = self.controller.config
        self.window_lbl.setText(
            f"Window: {cfg.start_time_s*1e3:+.4g} to {cfg.stop_time_s*1e3:+.4g} ms")
        self.nsamp_lbl.setText(f"N = {cfg.num_samples:,} samples")

    # ---------- actions ----------
    def _toggle_connect(self):
        if self.controller.connected:
            self.stop_acquisition()
            self.controller.disconnect()
            self.status_lbl.setText("Disconnected")
            self.connect_btn.setText("Connect")
        else:
            self._read_config_from_controls()
            ok = self.controller.connect()
            if ok:
                self.controller.apply_config()
                self.status_lbl.setText(f"Connected: {self.controller.config.serial_number}")
                self.connect_btn.setText("Disconnect")
            else:
                self.status_lbl.setText("Connection failed")
                QtWidgets.QMessageBox.warning(self, "Connect", "Failed to connect to the scope.")
        self._set_running_state(False)

    def start_continuous(self):
        self._start_worker(continuous=True)

    def start_single(self):
        self._start_worker(continuous=False)

    def _start_worker(self, continuous):
        if not self.controller.connected:
            QtWidgets.QMessageBox.information(self, "Not connected", "Connect to the scope first.")
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self._read_config_from_controls()
        self._continuous = continuous
        self.worker = DemodAcquisitionWorker(self.controller, continuous=continuous)
        self.worker.frameReady.connect(self._on_frame)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_done)
        self._set_running_state(True)
        self.worker.start()

    def stop_acquisition(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(2000)

    def _on_worker_done(self):
        self._set_running_state(False)

    def _on_failed(self, msg):
        self.status_lbl.setText(msg)

    def _on_frame(self, payload):
        # Always release the worker when done (even on error) so a continuous run
        # can acquire the next frame; otherwise the gated loop would hang.
        try:
            t, channels, metrics = payload
            for i in range(4):
                self.curves[i].setData(t, channels[i])
            self._draw_envelope(t, channels[0])
            self._compute_demod(t, channels)
        finally:
            if self.worker is not None:
                self.worker.notify_processed()

    def _set_running_state(self, running):
        if not running:
            self._continuous = False
        self.connect_btn.setEnabled(not running)
        self.run_btn.setEnabled(not running)
        self.single_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def closeEvent(self, event):
        self.stop_acquisition()
        if self.controller.connected:
            self.controller.disconnect()
        super().closeEvent(event)


def main(simulate=False):
    if "--simulate" in sys.argv or "-s" in sys.argv:
        simulate = True
    app = QtWidgets.QApplication(sys.argv)
    win = HeterodyneViewer(simulate=simulate)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

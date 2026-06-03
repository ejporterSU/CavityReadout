"""Analysis-mode framework for the readout GUI.

A "mode" is a self-contained way of looking at the scope: it owns a control
panel (the swappable left-panel section), decides what gets drawn on the shared
plot, and handles each acquired frame. `FreeViewMode` is the original live
waveform view; analysis modes (the first being `LorentzianFitMode`) subclass
`AnalysisMode`. Adding a new mode = write one subclass and register it in the
`ScopeWindow.modes` list.

Modes operate on a host window (`ScopeWindow`) passed in at construction; they
never `import gui`, so there's no circular import. From the host they use:
`controller`, `plot`, `curves`, the acquisition helpers
(`start_continuous`/`start_single`/`stop_acquisition`), `autoscale_x/y`,
`save_display`/`save_full`, `decimate_display`, and `fmt_hz`.
"""

import time

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from controller import CH_NAMES
from analysis import fit_lorentzian, compute_spectrum, fit_window_asymmetry


def _fmt_s(seconds):
    """Format a duration with an SI time unit (s/ms/us/ns)."""
    if not np.isfinite(seconds):
        return "-"
    a = abs(seconds)
    for div, unit in [(1.0, "s"), (1e-3, "ms"), (1e-6, "µs"), (1e-9, "ns")]:
        if a >= div:
            return f"{seconds/div:.4g} {unit}"
    return f"{seconds/1e-9:.4g} ns"


class AnalysisMode:
    """Base class. Subclasses build a panel, react to activation, and handle frames."""

    name = "Base"

    def __init__(self, host):
        self.host = host           # ScopeWindow

    def build_panel(self):
        """Return the QWidget shown in the mode stack for this mode (built once)."""
        raise NotImplementedError

    def activate(self):
        """Called when this mode becomes active (set curve visibility, add overlays)."""

    def deactivate(self):
        """Called when leaving this mode (remove overlays, restore shared state).
        Must be idempotent."""

    def on_frame(self, t, channels, metrics):
        """Handle one acquired frame: update the plot and any readouts."""

    def set_running_state(self, running, continuous):
        """Enable/disable this mode's action buttons for the given run state."""


class FreeViewMode(AnalysisMode):
    """The original live readout: every enabled channel, plus run/save/autoscale."""

    name = "Free View"

    def build_panel(self):
        panel = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)

        run_box = QtWidgets.QGroupBox("Run")
        rg = QtWidgets.QGridLayout(run_box)
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self.host.start_continuous)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self.host.stop_acquisition)
        self.single_btn = QtWidgets.QPushButton("Single")
        self.single_btn.clicked.connect(self.host.start_single)
        rg.addWidget(self.run_btn, 0, 0)
        rg.addWidget(self.stop_btn, 0, 1)
        rg.addWidget(self.single_btn, 0, 2)
        v.addWidget(run_box)

        disp_box = QtWidgets.QGroupBox("Display")
        dg = QtWidgets.QHBoxLayout(disp_box)
        autox_btn = QtWidgets.QPushButton("Auto X (full range)")
        autox_btn.clicked.connect(self.host.autoscale_x)
        autoy_btn = QtWidgets.QPushButton("Auto Y (measured)")
        autoy_btn.clicked.connect(self.host.autoscale_y)
        dg.addWidget(autox_btn)
        dg.addWidget(autoy_btn)
        v.addWidget(disp_box)

        save_box = QtWidgets.QGroupBox("Save (.npz)")
        sg = QtWidgets.QHBoxLayout(save_box)
        self.save_disp_btn = QtWidgets.QPushButton("Save display")
        self.save_disp_btn.setToolTip("Save the decimated trace as displayed "
                                      "(≤ 5000 points/channel).")
        self.save_disp_btn.clicked.connect(self.host.save_display)
        self.save_full_btn = QtWidgets.QPushButton("Save full")
        self.save_full_btn.setToolTip("Save the full-resolution capture.")
        self.save_full_btn.clicked.connect(self.host.save_full)
        sg.addWidget(self.save_disp_btn)
        sg.addWidget(self.save_full_btn)
        v.addWidget(save_box)

        self.metrics_lbl = QtWidgets.QLabel("No data yet.")
        self.metrics_lbl.setWordWrap(True)
        v.addWidget(self.metrics_lbl)
        return panel

    def activate(self):
        # redraw the last frame so switching back shows data immediately
        cap = self.host.controller.last_capture
        if cap is not None:
            t, channels = cap
            self._draw(t, channels)

    def _draw(self, t, channels):
        for i in range(4):
            if self.host.controller.config.enabled[i]:
                td, yd = self.host.decimate_display(t, channels[i])
                self.host.curves[i].setData(td, yd)
            else:
                self.host.curves[i].setData([], [])

    def on_frame(self, t, channels, metrics):
        self._draw(t, channels)
        self.metrics_lbl.setText(
            f"N = {metrics['n']:,}   fs = {self.host.fmt_hz(metrics['fs'])}\n"
            f"dt = {metrics['dt']*1e9:.2f} ns   span = {metrics['duration']*1e3:.3f} ms")

    def set_running_state(self, running, continuous):
        connected = self.host.controller.connected
        self.run_btn.setEnabled(connected and not running)
        self.single_btn.setEnabled(connected and not running)
        self.stop_btn.setEnabled(running and continuous)


class LorentzianFitMode(AnalysisMode):
    """Fit a Lorentzian to one channel of a single capture and report the result."""

    name = "Lorentzian Fit"

    def __init__(self, host):
        super().__init__(host)
        self.fit_curve = pg.PlotDataItem(pen=pg.mkPen("k", width=2,
                                                      style=pg.QtCore.Qt.DashLine))
        # Track which ViewBox currently owns the fit overlay so we can remove it
        # cleanly and move it when the selected channel switches sides (A/B ↔ C/D).
        self._fit_vb = None

    def build_panel(self):
        panel = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)

        box = QtWidgets.QGroupBox("Lorentzian fit")
        g = QtWidgets.QGridLayout(box)
        g.addWidget(QtWidgets.QLabel("Channel"), 0, 0)
        self.ch_combo = QtWidgets.QComboBox()
        self.ch_combo.addItems(CH_NAMES)
        self.ch_combo.currentIndexChanged.connect(self._on_channel_changed)
        g.addWidget(self.ch_combo, 0, 1)
        self.fit_btn = QtWidgets.QPushButton("Acquire && Fit")
        self.fit_btn.clicked.connect(self.host.start_single)
        g.addWidget(self.fit_btn, 1, 0, 1, 2)
        v.addWidget(box)

        self.result_lbl = QtWidgets.QLabel("No fit yet. Connect, then Acquire && Fit.")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setTextInteractionFlags(pg.QtCore.Qt.TextSelectableByMouse)
        v.addWidget(self.result_lbl)
        return panel

    def _selected(self):
        return self.ch_combo.currentIndex()

    def _on_channel_changed(self, *args):
        # The dashed fit overlay must live on the same ViewBox as the channel
        # it's fitting; A/B render on the left VB, C/D on the right.
        self._attach_fit_to_selected()
        cap = self.host.controller.last_capture
        if cap is not None:
            t, channels = cap
            self.on_frame(t, channels, None)

    def _attach_fit_to_selected(self):
        target = self.host._viewbox_for(self._selected())
        if self._fit_vb is target:
            return
        if self._fit_vb is not None:
            self._fit_vb.removeItem(self.fit_curve)
        target.addItem(self.fit_curve)
        self._fit_vb = target

    def activate(self):
        # default to the first enabled channel
        for i in range(4):
            if self.host.controller.config.enabled[i]:
                self.ch_combo.setCurrentIndex(i)
                break
        self._attach_fit_to_selected()
        cap = self.host.controller.last_capture
        if cap is not None:
            t, channels = cap
            self.on_frame(t, channels, None)
        else:
            self._show_only_selected_blank()

    def deactivate(self):
        if self._fit_vb is not None:
            self._fit_vb.removeItem(self.fit_curve)
            self._fit_vb = None
        self.fit_curve.setData([], [])

    def _show_only_selected_blank(self):
        sel = self._selected()
        for i in range(4):
            if i != sel:
                self.host.curves[i].setData([], [])

    def on_frame(self, t, channels, metrics):
        sel = self._selected()
        # show only the channel being analyzed
        for i in range(4):
            if i == sel:
                td, yd = self.host.decimate_display(t, channels[i])
                self.host.curves[i].setData(td, yd)
            else:
                self.host.curves[i].setData([], [])

        # fit on the full-resolution channel, regardless of display decimation
        res = fit_lorentzian(t, channels[sel])
        name = CH_NAMES[sel]
        if not res["success"]:
            self.fit_curve.setData([], [])
            self.result_lbl.setText(f"Ch {name}: fit failed.\n{res['message']}")
            return

        self.fit_curve.setData(res["t_fit"], res["y_fit"])
        p, e = res["params"], res["perr"]
        warn = "⚠ poor fit — not Lorentzian?\n" if res["r2"] < 0.8 else ""
        self.result_lbl.setText(
            warn +
            f"Ch {name} Lorentzian fit\n"
            f"center t0 = {_fmt_s(p['t0'])}  ± {_fmt_s(e['t0'])}\n"
            f"FWHM      = {_fmt_s(p['fwhm'])}  ± {_fmt_s(e['fwhm'])}\n"
            f"amplitude = {p['amp']:.4g} V  ± {e['amp']:.2g}\n"
            f"offset    = {p['offset']:.4g} V  ± {e['offset']:.2g}\n"
            f"R² = {res['r2']:.4f}   RMS resid = {res['rms']*1e3:.4g} mV")

    def set_running_state(self, running, continuous):
        connected = self.host.controller.connected
        self.fit_btn.setEnabled(connected and not running)


class FFTMode(AnalysisMode):
    """Live single-channel spectrum analyzer drawn on the host's FFT plot.

    Shows the one-sided spectrum of one selected channel (amplitude V or ASD
    V/√Hz, linear or dB) computed with a selectable window. The time-domain plot
    above keeps showing the same channel; the FFT plot occupies the bottom pane
    only while this mode is active."""

    name = "FFT View"

    _WINDOWS = ["Hann", "Hamming", "Blackman", "Rectangular"]

    def __init__(self, host):
        super().__init__(host)
        self.fft_curve = pg.PlotDataItem(pen=pg.mkPen("b", width=1))
        self._on_plot = False
        self._last_f = None        # cached freq axis for "Full (Nyquist)"

    def build_panel(self):
        panel = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)

        run_box = QtWidgets.QGroupBox("Run")
        rg = QtWidgets.QGridLayout(run_box)
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self.host.start_continuous)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self.host.stop_acquisition)
        self.single_btn = QtWidgets.QPushButton("Single")
        self.single_btn.clicked.connect(self.host.start_single)
        rg.addWidget(self.run_btn, 0, 0)
        rg.addWidget(self.stop_btn, 0, 1)
        rg.addWidget(self.single_btn, 0, 2)
        v.addWidget(run_box)

        box = QtWidgets.QGroupBox("Spectrum")
        g = QtWidgets.QGridLayout(box)
        g.addWidget(QtWidgets.QLabel("Channel"), 0, 0)
        self.ch_combo = QtWidgets.QComboBox()
        self.ch_combo.addItems(CH_NAMES)
        self.ch_combo.currentIndexChanged.connect(self._rerender)
        g.addWidget(self.ch_combo, 0, 1)

        g.addWidget(QtWidgets.QLabel("Quantity"), 1, 0)
        self.qty_combo = QtWidgets.QComboBox()
        self.qty_combo.addItems(["Amplitude (V)", "ASD (V/√Hz)"])
        self.qty_combo.currentIndexChanged.connect(self._rerender)
        g.addWidget(self.qty_combo, 1, 1)

        g.addWidget(QtWidgets.QLabel("Scale"), 2, 0)
        self.scale_combo = QtWidgets.QComboBox()
        self.scale_combo.addItems(["Linear", "dB"])
        self.scale_combo.currentIndexChanged.connect(self._rerender)
        g.addWidget(self.scale_combo, 2, 1)

        g.addWidget(QtWidgets.QLabel("Window"), 3, 0)
        self.window_combo = QtWidgets.QComboBox()
        self.window_combo.addItems(self._WINDOWS)
        self.window_combo.currentIndexChanged.connect(self._rerender)
        g.addWidget(self.window_combo, 3, 1)
        v.addWidget(box)

        range_box = QtWidgets.QGroupBox("Frequency range")
        rgb = QtWidgets.QGridLayout(range_box)
        self.fmin_spin = QtWidgets.QDoubleSpinBox()
        self.fmin_spin.setRange(0.0, 5000.0); self.fmin_spin.setDecimals(6)
        self.fmin_spin.setSuffix(" MHz")
        self.fmin_spin.valueChanged.connect(self._apply_freq_range)
        self.fmax_spin = QtWidgets.QDoubleSpinBox()
        self.fmax_spin.setRange(0.0, 5000.0); self.fmax_spin.setDecimals(6)
        self.fmax_spin.setSuffix(" MHz")
        self.fmax_spin.valueChanged.connect(self._apply_freq_range)
        self.full_btn = QtWidgets.QPushButton("Full (Nyquist)")
        self.full_btn.clicked.connect(self._full_range)
        self.autoy_btn = QtWidgets.QPushButton("Auto Y")
        self.autoy_btn.clicked.connect(self._fft_autoscale_y)
        rgb.addWidget(QtWidgets.QLabel("Min"), 0, 0)
        rgb.addWidget(self.fmin_spin, 0, 1)
        rgb.addWidget(QtWidgets.QLabel("Max"), 1, 0)
        rgb.addWidget(self.fmax_spin, 1, 1)
        rgb.addWidget(self.full_btn, 2, 0)
        rgb.addWidget(self.autoy_btn, 2, 1)
        v.addWidget(range_box)

        self.readout_lbl = QtWidgets.QLabel("No data yet. Connect, then Run.")
        self.readout_lbl.setWordWrap(True)
        v.addWidget(self.readout_lbl)
        return panel

    # ---- control state helpers ----
    def _selected(self):
        return self.ch_combo.currentIndex()

    def _scaling(self):
        return "asd" if self.qty_combo.currentIndex() == 1 else "amplitude"

    def _window(self):
        return self.window_combo.currentText().lower()

    def _rerender(self, *args):
        cap = self.host.controller.last_capture
        if cap is not None:
            t, channels = cap
            self.on_frame(t, channels, None)

    # ---- activation ----
    def activate(self):
        for i in range(4):
            if self.host.controller.config.enabled[i]:
                self.ch_combo.setCurrentIndex(i)
                break
        self.host.show_fft_panel(True)
        if not self._on_plot:
            self.host.fft_plot.addItem(self.fft_curve)
            self._on_plot = True
        cap = self.host.controller.last_capture
        if cap is not None:
            t, channels = cap
            self.on_frame(t, channels, None)
        else:
            self._show_only_selected_blank()

    def deactivate(self):
        if self._on_plot:
            self.host.fft_plot.removeItem(self.fft_curve)
            self._on_plot = False
        self.fft_curve.setData([], [])
        self.host.show_fft_panel(False)

    def _show_only_selected_blank(self):
        sel = self._selected()
        for i in range(4):
            if i != sel:
                self.host.curves[i].setData([], [])

    # ---- frame handling / drawing ----
    def on_frame(self, t, channels, metrics):
        sel = self._selected()
        for i in range(4):
            if i == sel:
                td, yd = self.host.decimate_display(t, channels[i])
                self.host.curves[i].setData(td, yd)
            else:
                self.host.curves[i].setData([], [])

        res = compute_spectrum(t, channels[sel], window=self._window(),
                               scaling=self._scaling())
        name = CH_NAMES[sel]
        if not res["success"]:
            self.fft_curve.setData([], [])
            self.readout_lbl.setText(f"Ch {name}: {res['message']}")
            return

        f, mag, units = res["f"], res["mag"], res["units"]
        self._last_f = f
        if self.scale_combo.currentText() == "dB":
            ref = float(np.max(mag)) if mag.size else 0.0
            floor = ref * 1e-12 if ref > 0 else 1e-12
            ydata = 20.0 * np.log10(np.maximum(mag, floor))
            ylabel = "dBV" if units == "V" else f"dB({units})"
        else:
            ydata = mag
            ylabel = units
        self.fft_curve.setData(f, ydata)
        self.host.fft_plot.setLabel("left", ylabel)

        self.readout_lbl.setText(
            f"Ch {name} spectrum\n"
            f"fs = {self.host.fmt_hz(res['fs'])}   Nyquist = {self.host.fmt_hz(res['nyquist'])}\n"
            f"df = {self.host.fmt_hz(res['df'])}   ENBW = {self.host.fmt_hz(res['enbw'])}\n"
            f"window = {self.window_combo.currentText()}")

    # ---- frequency range / autoscale ----
    def _apply_freq_range(self, *args):
        lo = self.fmin_spin.value() * 1e6
        hi = self.fmax_spin.value() * 1e6
        if hi > lo:
            self.host.fft_plot.setXRange(lo, hi, padding=0)

    def _full_range(self):
        if self._last_f is None or self._last_f.size == 0:
            return
        fmax = float(self._last_f[-1])
        self.host.fft_plot.setXRange(0.0, fmax, padding=0)
        self._loading = True
        self.fmin_spin.setValue(0.0)
        self.fmax_spin.setValue(fmax / 1e6)
        self._loading = False

    def _fft_autoscale_y(self):
        """Fit the FFT y-axis to the data within the visible frequency range."""
        data = self.fft_curve.getData()
        if data is None or data[0] is None or len(data[0]) == 0:
            return
        f, y = np.asarray(data[0]), np.asarray(data[1])
        (lo, hi), _ = self.host.fft_plot.viewRange()
        mask = (f >= lo) & (f <= hi)
        if not np.any(mask):
            mask = np.ones(f.size, dtype=bool)
        ymin, ymax = float(np.min(y[mask])), float(np.max(y[mask]))
        if ymin == ymax:
            pad = abs(ymin) * 0.1 or 0.5
            ymin, ymax = ymin - pad, ymax + pad
        self.host.fft_plot.setYRange(ymin, ymax, padding=0.05)

    def set_running_state(self, running, continuous):
        connected = self.host.controller.connected
        self.run_btn.setEnabled(connected and not running)
        self.single_btn.setEnabled(connected and not running)
        self.stop_btn.setEnabled(running and continuous)


class VRSAlignmentMode(AnalysisMode):
    """VRS–cavity alignment sweep.

    Each triggered shot holds two TTL-gated windows on the signal channel: a
    *double* Lorentzian (the VRS doublet) then a *single* Lorentzian (bare
    cavity). The asymmetry = (doublet center − single center), scaled to kHz, is
    plotted against the cavity frequency you step externally between shots; a
    line fit gives the zero-crossing — the cavity frequency where the atomic line
    sits on resonance.

    Workflow: set the acquisition mode to "Triggered", then Start Analysis. The
    mode arms a continuous triggered run and treats every *successful* shot as
    the next sweep point, so the sweep advances once per trigger while you retune
    the cavity. Failed shots (wrong TTL count, short window, bad/low-R² fit) are
    reported and do not advance — retrigger at the same cavity setting. The
    asymmetry-vs-frequency scatter, line fit, and zero-crossing are drawn on the
    bottom (shared FFT) pane.
    """

    name = "VRS Alignment"

    def __init__(self, host):
        super().__init__(host)
        # Fit overlays drawn on the signal channel's ViewBox.
        self.double_curve = pg.PlotDataItem(
            pen=pg.mkPen("r", width=2, style=pg.QtCore.Qt.DashLine))
        self.single_curve = pg.PlotDataItem(
            pen=pg.mkPen("m", width=2, style=pg.QtCore.Qt.DashLine))
        self._sig_vb = None
        # Secondary-plot items: asymmetry vs cavity frequency.
        self._scatter = pg.ScatterPlotItem(size=9, brush=pg.mkBrush(30, 30, 200),
                                            pen=pg.mkPen("k"))
        self._errbars = pg.ErrorBarItem(pen=pg.mkPen(30, 30, 200))
        self._fit_line = pg.PlotDataItem(
            pen=pg.mkPen("r", width=2, style=pg.QtCore.Qt.DashLine))
        self._href = pg.InfiniteLine(pos=0.0, angle=0,
                                     pen=pg.mkPen((150, 150, 150),
                                                  style=pg.QtCore.Qt.DashLine))
        self._zero_marker = pg.InfiniteLine(
            angle=90, pen=pg.mkPen((0, 150, 0), width=2,
                                   style=pg.QtCore.Qt.DashLine))
        self._zero_marker.setVisible(False)
        self._on_plot = False
        self._saved_labels = None
        self._sweeping = False
        self._t0 = None
        self._success = []          # list of (freq_mhz, asymm_khz, err_khz)
        self._fail_count = 0

    # ---- panel ----
    @staticmethod
    def _spin(lo, hi, decimals, suffix, val, step=None):
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(decimals)
        s.setValue(val)
        if suffix:
            s.setSuffix(suffix)
        if step is not None:
            s.setSingleStep(step)
        return s

    def build_panel(self):
        panel = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)

        ch_box = QtWidgets.QGroupBox("Channels")
        cg = QtWidgets.QGridLayout(ch_box)
        cg.addWidget(QtWidgets.QLabel("Signal"), 0, 0)
        self.sig_combo = QtWidgets.QComboBox()
        self.sig_combo.addItems(CH_NAMES)
        self.sig_combo.currentIndexChanged.connect(self._on_chan_changed)
        cg.addWidget(self.sig_combo, 0, 1)
        cg.addWidget(QtWidgets.QLabel("TTL"), 1, 0)
        self.ttl_combo = QtWidgets.QComboBox()
        self.ttl_combo.addItems(CH_NAMES)
        self.ttl_combo.currentIndexChanged.connect(self._on_chan_changed)
        cg.addWidget(self.ttl_combo, 1, 1)
        v.addWidget(ch_box)

        win_box = QtWidgets.QGroupBox("Time window (crop)")
        wg = QtWidgets.QGridLayout(win_box)
        self.win_lo = self._spin(-10000.0, 10000.0, 4, " ms", 0.0)
        self.win_hi = self._spin(-10000.0, 10000.0, 4, " ms", 0.0)
        tip = ("Crop captures to [start, stop] before analysis.\n"
               "Leave stop ≤ start to use the whole capture.")
        self.win_lo.setToolTip(tip)
        self.win_hi.setToolTip(tip)
        wg.addWidget(QtWidgets.QLabel("Start"), 0, 0)
        wg.addWidget(self.win_lo, 0, 1)
        wg.addWidget(QtWidgets.QLabel("Stop"), 1, 0)
        wg.addWidget(self.win_hi, 1, 1)
        v.addWidget(win_box)

        ttl_box = QtWidgets.QGroupBox("TTL gating")
        tg = QtWidgets.QGridLayout(ttl_box)
        self.thresh_spin = self._spin(-100.0, 100.0, 3, " V", 1.0)
        self.minw_spin = self._spin(0.0, 10000.0, 4, " ms", 0.0)
        tg.addWidget(QtWidgets.QLabel("Threshold"), 0, 0)
        tg.addWidget(self.thresh_spin, 0, 1)
        tg.addWidget(QtWidgets.QLabel("Min width"), 1, 0)
        tg.addWidget(self.minw_spin, 1, 1)
        v.addWidget(ttl_box)

        scale_box = QtWidgets.QGroupBox("Scan scaling (time → kHz)")
        sg = QtWidgets.QGridLayout(scale_box)
        self.range_spin = self._spin(0.0, 1e6, 6, " MHz", 1.0)
        self.scant_spin = self._spin(1e-6, 1e6, 6, " ms", 1.0)
        sg.addWidget(QtWidgets.QLabel("Scan range"), 0, 0)
        sg.addWidget(self.range_spin, 0, 1)
        sg.addWidget(QtWidgets.QLabel("Scan time"), 1, 0)
        sg.addWidget(self.scant_spin, 1, 1)
        v.addWidget(scale_box)

        sweep_box = QtWidgets.QGroupBox("Cavity sweep")
        qg = QtWidgets.QGridLayout(sweep_box)
        self.start_spin = self._spin(-1e6, 1e6, 6, " MHz", 0.0)
        self.step_spin = self._spin(-1e6, 1e6, 6, " MHz", 1.0)
        self.nsteps_spin = QtWidgets.QSpinBox()
        self.nsteps_spin.setRange(2, 100000)
        self.nsteps_spin.setValue(11)
        self.gof_spin = self._spin(0.0, 1.0, 2, "", 0.5, step=0.05)
        qg.addWidget(QtWidgets.QLabel("Start"), 0, 0)
        qg.addWidget(self.start_spin, 0, 1)
        qg.addWidget(QtWidgets.QLabel("Step"), 1, 0)
        qg.addWidget(self.step_spin, 1, 1)
        qg.addWidget(QtWidgets.QLabel("Num steps"), 2, 0)
        qg.addWidget(self.nsteps_spin, 2, 1)
        qg.addWidget(QtWidgets.QLabel("Min R²"), 3, 0)
        qg.addWidget(self.gof_spin, 3, 1)
        v.addWidget(sweep_box)

        btn_row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start Analysis")
        self.start_btn.clicked.connect(self._start_sweep)
        self.reset_btn = QtWidgets.QPushButton("Reset")
        self.reset_btn.clicked.connect(self._reset_sweep)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.reset_btn)
        v.addLayout(btn_row)

        self.total_lbl = QtWidgets.QLabel("Total time: 0.0 s")
        v.addWidget(self.total_lbl)
        self.status_lbl = QtWidgets.QLabel("Idle. Set Triggered acquisition, then Start.")
        self.status_lbl.setWordWrap(True)
        v.addWidget(self.status_lbl)
        self.result_lbl = QtWidgets.QLabel("")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setTextInteractionFlags(pg.QtCore.Qt.TextSelectableByMouse)
        v.addWidget(self.result_lbl)

        self._inputs = [self.sig_combo, self.ttl_combo, self.win_lo, self.win_hi,
                        self.thresh_spin, self.minw_spin, self.range_spin,
                        self.scant_spin, self.start_spin, self.step_spin,
                        self.nsteps_spin, self.gof_spin]
        return panel

    # ---- selection / overlay helpers ----
    def _sig_idx(self):
        return self.sig_combo.currentIndex()

    def _ttl_idx(self):
        return self.ttl_combo.currentIndex()

    def _attach_overlays(self):
        target = self.host._viewbox_for(self._sig_idx())
        if self._sig_vb is target:
            return
        if self._sig_vb is not None:
            self._sig_vb.removeItem(self.double_curve)
            self._sig_vb.removeItem(self.single_curve)
        target.addItem(self.double_curve)
        target.addItem(self.single_curve)
        self._sig_vb = target

    def _on_chan_changed(self, *args):
        self._attach_overlays()
        if not self._sweeping:
            cap = self.host.controller.last_capture
            if cap is not None:
                self._preview(*cap)

    # ---- activation ----
    def activate(self):
        cfg = self.host.controller.config
        try:
            ttl_default = CH_NAMES.index(cfg.trigger_channel)
        except ValueError:
            ttl_default = 3
        self.ttl_combo.setCurrentIndex(ttl_default)
        sig_default = next((i for i in range(4)
                            if cfg.enabled[i] and i != ttl_default), 0)
        self.sig_combo.setCurrentIndex(sig_default)

        self._attach_overlays()
        self.host.show_fft_panel(True)
        if not self._on_plot:
            p = self.host.fft_plot
            bottom, left = p.getAxis("bottom"), p.getAxis("left")
            self._saved_labels = (bottom.labelText, bottom.labelUnits,
                                  left.labelText, left.labelUnits)
            for it in (self._href, self._errbars, self._scatter,
                       self._fit_line, self._zero_marker):
                p.addItem(it)
            p.setLabel("bottom", "Cavity frequency (MHz)")
            p.setLabel("left", "Asymmetry (kHz)")
            p.enableAutoRange()
            self._on_plot = True

        cap = self.host.controller.last_capture
        if cap is not None:
            self._preview(*cap)
        else:
            for i in range(4):
                self.host.curves[i].setData([], [])

    def deactivate(self):
        if self._sweeping:
            self._sweeping = False
            self.host.stop_acquisition()
        if self._sig_vb is not None:
            self._sig_vb.removeItem(self.double_curve)
            self._sig_vb.removeItem(self.single_curve)
            self._sig_vb = None
        self.double_curve.setData([], [])
        self.single_curve.setData([], [])
        if self._on_plot:
            p = self.host.fft_plot
            for it in (self._href, self._errbars, self._scatter,
                       self._fit_line, self._zero_marker):
                p.removeItem(it)
            if self._saved_labels is not None:
                bt, bu, lt, lu = self._saved_labels
                p.setLabel("bottom", bt, units=bu)
                p.setLabel("left", lt, units=lu)
            self._on_plot = False
        self.host.show_fft_panel(False)

    # ---- frame handling ----
    def _preview(self, t, channels):
        """Live (non-sweeping) view: just show the signal + TTL traces."""
        si, ti = self._sig_idx(), self._ttl_idx()
        for i in range(4):
            if i in (si, ti):
                td, yd = self.host.decimate_display(t, channels[i])
                self.host.curves[i].setData(td, yd)
            else:
                self.host.curves[i].setData([], [])
        self.double_curve.setData([], [])
        self.single_curve.setData([], [])

    def _show_traces(self, t, sig, ttl):
        si, ti = self._sig_i, self._ttl_i
        for i in range(4):
            if i == si:
                td, yd = self.host.decimate_display(t, sig)
                self.host.curves[i].setData(td, yd)
            elif i == ti:
                td, yd = self.host.decimate_display(t, ttl)
                self.host.curves[i].setData(td, yd)
            else:
                self.host.curves[i].setData([], [])

    def _crop(self, t, sig, ttl):
        lo, hi = self._win_lo, self._win_hi
        if hi <= lo:
            return t, sig, ttl
        m = (t >= lo) & (t <= hi)
        return t[m], sig[m], ttl[m]

    def on_frame(self, t, channels, metrics):
        self._update_total()
        if not self._sweeping:
            self._preview(t, channels)
            return

        k = len(self._success)
        freq_k = self._start_mhz + k * self._step_mhz
        tw, sw, ttlw = self._crop(t, channels[self._sig_i], channels[self._ttl_i])
        self._show_traces(tw, sw, ttlw)

        if tw.size < 8:
            self._note_failure(k, freq_k, f"window too short ({tw.size} samples).")
            return

        res = fit_window_asymmetry(tw, sw, ttlw, self._scale,
                                   threshold=self._thresh, min_width=self._minw,
                                   gof_min=self._gof)
        if not res["success"]:
            self._note_failure(k, freq_k, res["message"])
            return

        self.double_curve.setData(res["t1"], res["y1_fit"])
        self.single_curve.setData(res["t2"], res["y2_fit"])
        self._success.append((freq_k, res["asymm_khz"], res["asymm_err_khz"]))
        self._update_scatter()

        done = len(self._success)
        if done >= self._n:
            self._finalize()
        else:
            nxt = self._start_mhz + done * self._step_mhz
            self.status_lbl.setText(
                f"Step {done}/{self._n} ok: {res['asymm_khz']:+.3f} ± "
                f"{res['asymm_err_khz']:.3f} kHz (R²={res['gof']:.3f}).\n"
                f"Set cavity to {nxt:g} MHz and trigger.  "
                f"({self._fail_count} failed)")

    def _note_failure(self, k, freq_k, reason):
        self._fail_count += 1
        self.double_curve.setData([], [])
        self.single_curve.setData([], [])
        self.status_lbl.setText(
            f"⚠ shot failed: {reason}\nStill at step {k+1}/{self._n} "
            f"(cavity {freq_k:g} MHz) — retrigger.  ({self._fail_count} failed)")

    def _update_scatter(self):
        arr = np.array(self._success, dtype=float)
        xs, ys, es = arr[:, 0], arr[:, 1], arr[:, 2]
        self._scatter.setData(xs, ys)
        h = np.where(np.isfinite(es), 2.0 * es, 0.0)
        beam = abs(self._step_mhz) * 0.2 or 0.1
        self._errbars.setData(x=xs, y=ys, height=h, beam=beam)

    def _update_total(self):
        if self._t0 is not None:
            self.total_lbl.setText(f"Total time: {time.monotonic() - self._t0:.1f} s")

    # ---- sweep control ----
    def _start_sweep(self):
        if not self.host.controller.connected:
            self.status_lbl.setText("Not connected — connect to the scope first.")
            return
        if self._sweeping:
            return
        if self._sig_idx() == self._ttl_idx():
            self.status_lbl.setText("Signal and TTL channels must differ.")
            return
        step = self.step_spin.value()
        if step == 0:
            self.status_lbl.setText("Step size must be non-zero.")
            return
        scan_time_s = self.scant_spin.value() * 1e-3
        if scan_time_s <= 0:
            self.status_lbl.setText("Scan time must be > 0.")
            return

        # Snapshot parameters for the whole sweep.
        self._sig_i = self._sig_idx()
        self._ttl_i = self._ttl_idx()
        self._win_lo = self.win_lo.value() * 1e-3
        self._win_hi = self.win_hi.value() * 1e-3
        self._thresh = self.thresh_spin.value()
        self._minw = self.minw_spin.value() * 1e-3
        self._scale = (self.range_spin.value() * 1e6 / scan_time_s) * 1e-3
        self._start_mhz = self.start_spin.value()
        self._step_mhz = step
        self._n = self.nsteps_spin.value()
        self._gof = self.gof_spin.value()

        self._success = []
        self._fail_count = 0
        self._clear_secondary()
        self.result_lbl.setText("")
        self.double_curve.setData([], [])
        self.single_curve.setData([], [])

        # One frame per trigger: drive a continuous run in Triggered mode.
        self.host.mode_combo.setCurrentText("Triggered")
        self._t0 = time.monotonic()
        self._sweeping = True
        self.status_lbl.setText(
            f"Step 1/{self._n} — set cavity to {self._start_mhz:g} MHz and trigger.")
        self._launch_run()

    def _launch_run(self):
        worker = getattr(self.host, "worker", None)
        if worker is not None and worker.isRunning():
            # Stop the stale run, then start once its finished() has flushed so the
            # queued not-running callback can't gray us out mid-sweep.
            self.host.stop_acquisition()
            pg.QtCore.QTimer.singleShot(0, self.host.start_continuous)
        else:
            self.host.start_continuous()

    def _reset_sweep(self):
        self._sweeping = False
        self.host.stop_acquisition()
        self._success = []
        self._fail_count = 0
        self._t0 = None
        self._clear_secondary()
        self.double_curve.setData([], [])
        self.single_curve.setData([], [])
        self.total_lbl.setText("Total time: 0.0 s")
        self.status_lbl.setText("Reset. Set Triggered acquisition, then Start.")
        self.result_lbl.setText("")
        # If no worker was running, stop_acquisition won't re-enable controls.
        worker = getattr(self.host, "worker", None)
        self.set_running_state(worker is not None and worker.isRunning(), True)

    def _clear_secondary(self):
        self._scatter.setData([], [])
        self._errbars.setData(x=np.array([]), y=np.array([]),
                              height=np.array([]), beam=0.0)
        self._fit_line.setData([], [])
        self._zero_marker.setVisible(False)

    def _finalize(self):
        self._sweeping = False
        self.host.stop_acquisition()
        self._update_total()

        arr = np.array(self._success, dtype=float)
        n = arr.shape[0]
        if n < 2:
            self.status_lbl.setText(
                f"Sweep stopped: need ≥2 valid points (got {n}, "
                f"{self._fail_count} failed).")
            return
        xs, ys, es = arr[:, 0], arr[:, 1], arr[:, 2]

        # Weight by 1/sigma where the fit gave a usable error; fall back to the
        # median error for points whose covariance was singular.
        good = np.isfinite(es) & (es > 0)
        w = 1.0 / np.where(good, es, np.median(es[good])) if good.any() else None

        cov = None
        try:
            coeffs, cov = np.polyfit(xs, ys, 1, w=w, cov=True)
        except (ValueError, np.linalg.LinAlgError):
            coeffs = np.polyfit(xs, ys, 1, w=w)
        m, c = float(coeffs[0]), float(coeffs[1])
        if m == 0:
            self.status_lbl.setText("Sweep complete, but slope ≈ 0 — no zero crossing.")
            return

        zero = -c / m
        if cov is not None and np.all(np.isfinite(cov)):
            var = (cov[1, 1] / m**2 + (c**2 / m**4) * cov[0, 0]
                   - 2.0 * (c / m**3) * cov[0, 1])
            dz = float(np.sqrt(var)) if var > 0 else float("nan")
        else:
            dz = float("nan")

        xspan = float(xs.max() - xs.min()) or 1.0
        xf = np.linspace(xs.min() - 0.05 * xspan, xs.max() + 0.05 * xspan, 200)
        self._fit_line.setData(xf, m * xf + c)
        self._zero_marker.setValue(zero)
        self._zero_marker.setVisible(True)

        self.status_lbl.setText(
            f"Sweep complete: {n} valid, {self._fail_count} failed.")
        self.result_lbl.setText(
            f"Optimal cavity frequency (asymmetry = 0):\n"
            f"   {zero:.4f} ± {dz:.4f} MHz\n"
            f"slope = {m:.4g} kHz/MHz,  intercept = {c:.4g} kHz")

    def set_running_state(self, running, continuous):
        self.start_btn.setEnabled(self.host.controller.connected and not running)
        for w in getattr(self, "_inputs", []):
            w.setEnabled(not running)

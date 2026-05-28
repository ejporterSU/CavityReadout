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

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from controller import CH_NAMES
from analysis import fit_lorentzian, compute_spectrum


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

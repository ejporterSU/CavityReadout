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
`save_last`, and `fmt_hz`.
"""

import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets

from controller import CH_NAMES
from analysis import fit_lorentzian


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

        self.save_btn = QtWidgets.QPushButton("Save last frame (.npz)")
        self.save_btn.clicked.connect(self.host.save_last)
        v.addWidget(self.save_btn)

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
                self.host.curves[i].setData(t, channels[i])
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
        self._on_plot = False

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
        # re-display from the last capture for the newly selected channel
        cap = self.host.controller.last_capture
        if cap is not None:
            t, channels = cap
            self.on_frame(t, channels, None)

    def activate(self):
        # default to the first enabled channel
        for i in range(4):
            if self.host.controller.config.enabled[i]:
                self.ch_combo.setCurrentIndex(i)
                break
        if not self._on_plot:
            self.host.plot.addItem(self.fit_curve)
            self._on_plot = True
        cap = self.host.controller.last_capture
        if cap is not None:
            t, channels = cap
            self.on_frame(t, channels, None)
        else:
            self._show_only_selected_blank()

    def deactivate(self):
        if self._on_plot:
            self.host.plot.removeItem(self.fit_curve)
            self._on_plot = False
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
                self.host.curves[i].setData(t, channels[i])
            else:
                self.host.curves[i].setData([], [])

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

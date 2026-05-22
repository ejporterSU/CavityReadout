"""PyQtGraph desktop app: a simplified Cleverscope readout.

Left panel sets the settings you care about (connection, run mode, trigger,
time base, per-channel range/coupling/enable); the right pane is a live
waveform plot. Both continuous "Run" and one-shot "Single" are first-class.

Acquisition is blocking, so it runs on a worker QThread; the GUI thread only
draws the frames the worker emits. Launch via run_scope.py (handles sys.path /
cwd / the DLL), or directly with `python gui.py --simulate`.
"""

import sys
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from controller import ScopeController, CH_NAMES, CH_COLORS, ACQ_MODES
from analysis_modes import FreeViewMode, LorentzianFitMode, FFTMode


class AcquisitionWorker(QtCore.QThread):
    """Runs acquisition off the GUI thread. In continuous mode it loops until
    stopped; in single mode it grabs one frame and finishes."""

    frameReady = QtCore.Signal(object)   # (t, channels, metrics)
    failed = QtCore.Signal(str)

    def __init__(self, controller, continuous, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._continuous = continuous
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            if self._controller.needs_apply():
                self._controller.apply_config()
            t, channels, metrics = self._controller.acquire_once()
            if t is None:
                self.failed.emit("Acquisition failed or timed out.")
                if not self._continuous:
                    return
            else:
                self.frameReady.emit((t, channels, metrics))
            if not self._continuous:
                return
            self.msleep(50)  # small breather between live frames


class HoverAxis(pg.AxisItem):
    """Axis that darkens on hover, signaling it's the one a drag-zoom will scale.

    pyqtgraph already zooms a single axis when you drag on it; this just adds the
    visual cue for which axis is under the cursor."""

    NORMAL = (120, 120, 120)
    HOVER = (0, 0, 0)

    def __init__(self, orientation, **kwargs):
        super().__init__(orientation, **kwargs)
        self.setAcceptHoverEvents(True)
        self._apply(self.NORMAL, 1)

    def _apply(self, color, width):
        self.setPen(pg.mkPen(color, width=width))
        self.setTextPen(pg.mkPen(color))

    def hoverEnterEvent(self, event):
        self._apply(self.HOVER, 2)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._apply(self.NORMAL, 1)
        super().hoverLeaveEvent(event)


class ScopeWindow(QtWidgets.QMainWindow):
    # Cap the points actually drawn for a waveform trace; the underlying capture
    # stays full-resolution (analysis and "Save full" use it). Purely a display
    # speed-up — fewer points to render per frame.
    MAX_DISPLAY_POINTS = 5000

    def __init__(self, simulate=False):
        super().__init__()
        self.setWindowTitle("Cleverscope Readout" + (" [SIMULATION]" if simulate else ""))
        self.resize(1140, 720)

        self.controller = ScopeController(simulate=simulate)
        self.worker = None
        self._continuous = False     # is the active run a continuous one?

        # analysis modes (Free View + analysis suite); registered before the
        # controls are built so their panels can populate the mode stack.
        self.modes = [FreeViewMode(self), LorentzianFitMode(self), FFTMode(self)]
        self.active_mode = self.modes[0]

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        plot = self._build_plot()           # sets self.plot / self.curves
        # The control panel can grow taller than the window (more so as analysis
        # modes are added), so put it in a scroll area: everything stays clickable
        # and the panel just scrolls instead of squeezing widgets out of reach.
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self._build_controls())
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setFixedWidth(352)            # 330 panel + room for the scrollbar
        layout.addWidget(scroll, 0)
        layout.addWidget(plot, 1)

        self._sync_controls_to_config()
        self._on_mode_changed(0)            # activate the initial mode
        self._set_running_state(False)

    # ---------- UI construction ----------
    def _build_controls(self):
        panel = QtWidgets.QWidget()
        panel.setMinimumWidth(320)
        v = QtWidgets.QVBoxLayout(panel)
        v.setSpacing(6)
        v.setContentsMargins(6, 6, 6, 6)

        # connection
        conn_box = QtWidgets.QGroupBox("Connection")
        cg = QtWidgets.QGridLayout(conn_box)
        self.serial_edit = QtWidgets.QLineEdit(self.controller.config.serial_number)
        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connect)
        self.status_lbl = QtWidgets.QLabel("Disconnected")
        cg.addWidget(QtWidgets.QLabel("Serial"), 0, 0)
        cg.addWidget(self.serial_edit, 0, 1)
        cg.addWidget(self.connect_btn, 1, 0, 1, 2)
        cg.addWidget(self.status_lbl, 2, 0, 1, 2)
        v.addWidget(conn_box)

        # acquisition mode (shared across all view/analysis modes)
        acq_box = QtWidgets.QGroupBox("Acquisition")
        ag = QtWidgets.QGridLayout(acq_box)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(ACQ_MODES)
        self.mode_combo.currentTextChanged.connect(self._on_config_changed)
        ag.addWidget(QtWidgets.QLabel("Mode"), 0, 0)
        ag.addWidget(self.mode_combo, 0, 1)
        v.addWidget(acq_box)

        # trigger
        trig_box = QtWidgets.QGroupBox("Trigger")
        tg = QtWidgets.QGridLayout(trig_box)
        self.trig_ch_combo = QtWidgets.QComboBox()
        self.trig_ch_combo.addItems(CH_NAMES)
        self.trig_ch_combo.currentTextChanged.connect(self._on_config_changed)
        self.trig_level_spin = QtWidgets.QDoubleSpinBox()
        self.trig_level_spin.setRange(-100.0, 100.0)
        self.trig_level_spin.setDecimals(3)
        self.trig_level_spin.setSingleStep(0.1)
        self.trig_level_spin.valueChanged.connect(self._on_config_changed)
        self.trig_slope_combo = QtWidgets.QComboBox()
        self.trig_slope_combo.addItems(["Rising", "Falling"])
        self.trig_slope_combo.currentTextChanged.connect(self._on_config_changed)
        tg.addWidget(QtWidgets.QLabel("Channel"), 0, 0)
        tg.addWidget(self.trig_ch_combo, 0, 1)
        tg.addWidget(QtWidgets.QLabel("Level (V)"), 1, 0)
        tg.addWidget(self.trig_level_spin, 1, 1)
        tg.addWidget(QtWidgets.QLabel("Slope"), 2, 0)
        tg.addWidget(self.trig_slope_combo, 2, 1)
        v.addWidget(trig_box)

        # time base
        tb_box = QtWidgets.QGroupBox("Time base")
        bg = QtWidgets.QGridLayout(tb_box)
        self.rate_combo = QtWidgets.QComboBox()
        self._rate_values = [400e6, 200e6, 100e6, 50e6, 20e6, 10e6, 1e6,
                             400e3, 200e3, 100e3]
        self.rate_combo.addItems([self.fmt_hz(r) for r in self._rate_values])
        self.rate_combo.currentIndexChanged.connect(self._on_config_changed)
        self.start_spin = QtWidgets.QDoubleSpinBox()
        self.start_spin.setRange(-1000.0, 1000.0)
        self.start_spin.setDecimals(3)
        self.start_spin.setSuffix(" ms")
        self.start_spin.valueChanged.connect(self._on_config_changed)
        self.stop_spin = QtWidgets.QDoubleSpinBox()
        self.stop_spin.setRange(-1000.0, 1000.0)
        self.stop_spin.setDecimals(3)
        self.stop_spin.setSuffix(" ms")
        self.stop_spin.valueChanged.connect(self._on_config_changed)
        self.nsamp_lbl = QtWidgets.QLabel("")
        bg.addWidget(QtWidgets.QLabel("Rate"), 0, 0)
        bg.addWidget(self.rate_combo, 0, 1)
        bg.addWidget(QtWidgets.QLabel("Start"), 1, 0)
        bg.addWidget(self.start_spin, 1, 1)
        bg.addWidget(QtWidgets.QLabel("Stop"), 2, 0)
        bg.addWidget(self.stop_spin, 2, 1)
        bg.addWidget(self.nsamp_lbl, 3, 0, 1, 2)
        v.addWidget(tb_box)

        # channels
        ch_box = QtWidgets.QGroupBox("Channels")
        cg2 = QtWidgets.QGridLayout(ch_box)
        cg2.addWidget(QtWidgets.QLabel("On"), 0, 0)
        cg2.addWidget(QtWidgets.QLabel("Ch"), 0, 1)
        cg2.addWidget(QtWidgets.QLabel("Min"), 0, 2)
        cg2.addWidget(QtWidgets.QLabel("Max"), 0, 3)
        cg2.addWidget(QtWidgets.QLabel("Cpl"), 0, 4)
        self.ch_enable = []
        self.ch_min = []
        self.ch_max = []
        self.ch_coupling = []
        for i, name in enumerate(CH_NAMES):
            en = QtWidgets.QCheckBox()
            en.toggled.connect(self._on_config_changed)
            lbl = QtWidgets.QLabel(name)
            lbl.setStyleSheet(f"color: {CH_COLORS[i]}; font-weight: bold;")
            mn = QtWidgets.QDoubleSpinBox(); mn.setRange(-100, 100); mn.setDecimals(3)
            mn.valueChanged.connect(self._on_config_changed)
            mx = QtWidgets.QDoubleSpinBox(); mx.setRange(-100, 100); mx.setDecimals(3)
            mx.valueChanged.connect(self._on_config_changed)
            cpl = QtWidgets.QComboBox(); cpl.addItems(["AC", "DC"])
            cpl.currentTextChanged.connect(self._on_config_changed)
            row = i + 1
            cg2.addWidget(en, row, 0)
            cg2.addWidget(lbl, row, 1)
            cg2.addWidget(mn, row, 2)
            cg2.addWidget(mx, row, 3)
            cg2.addWidget(cpl, row, 4)
            self.ch_enable.append(en)
            self.ch_min.append(mn)
            self.ch_max.append(mx)
            self.ch_coupling.append(cpl)
        v.addWidget(ch_box)

        # mode selector + swappable per-mode panel (Free View / analysis modes)
        mode_box = QtWidgets.QGroupBox("Mode")
        mg = QtWidgets.QVBoxLayout(mode_box)
        self.analysis_combo = QtWidgets.QComboBox()
        self.analysis_combo.addItems([m.name for m in self.modes])
        self.analysis_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.mode_stack = QtWidgets.QStackedWidget()
        for m in self.modes:
            self.mode_stack.addWidget(m.build_panel())
        mg.addWidget(self.analysis_combo)
        mg.addWidget(self.mode_stack)
        v.addWidget(mode_box)

        v.addStretch(1)
        return panel

    def _build_plot(self):
        pg.setConfigOptions(antialias=True)
        self.plot = pg.PlotWidget(axisItems={"bottom": HoverAxis("bottom"),
                                             "left": HoverAxis("left")})
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Voltage", units="V")
        self.plot.addLegend()
        self.curves = []
        for i, name in enumerate(CH_NAMES):
            curve = self.plot.plot(pen=pg.mkPen(CH_COLORS[i], width=1), name=f"Ch {name}")
            curve.setDownsampling(auto=True)
            curve.setClipToView(True)
            self.curves.append(curve)

        # FFT plot lives in the bottom pane, hidden until FFT View mode reveals it.
        self.fft_plot = pg.PlotWidget(axisItems={"bottom": HoverAxis("bottom"),
                                                 "left": HoverAxis("left")})
        self.fft_plot.setBackground("w")
        self.fft_plot.showGrid(x=True, y=True, alpha=0.3)
        self.fft_plot.setLabel("bottom", "Frequency", units="Hz")
        self.fft_plot.setLabel("left", "Magnitude")
        self.fft_plot.hide()

        self.plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.plot_splitter.addWidget(self.plot)
        self.plot_splitter.addWidget(self.fft_plot)
        return self.plot_splitter

    # ---------- config <-> widgets ----------
    def _sync_controls_to_config(self):
        cfg = self.controller.config
        self._loading = True
        self.serial_edit.setText(cfg.serial_number)
        self.mode_combo.setCurrentText(cfg.acq_mode)
        self.trig_ch_combo.setCurrentText(cfg.trigger_channel)
        self.trig_level_spin.setValue(cfg.trigger_level_v)
        self.trig_slope_combo.setCurrentText(cfg.trigger_slope)
        nearest = min(range(len(self._rate_values)),
                      key=lambda k: abs(self._rate_values[k] - cfg.sampling_rate_hz))
        self.rate_combo.setCurrentIndex(nearest)
        self.start_spin.setValue(cfg.start_time_s * 1e3)
        self.stop_spin.setValue(cfg.stop_time_s * 1e3)
        for i in range(4):
            self.ch_enable[i].setChecked(cfg.enabled[i])
            self.ch_min[i].setValue(cfg.ranges[i][0])
            self.ch_max[i].setValue(cfg.ranges[i][1])
            self.ch_coupling[i].setCurrentText(cfg.couplings[i])
        self._loading = False
        self._update_nsamp_label()

    def _read_config_from_controls(self):
        cfg = self.controller.config
        cfg.serial_number = self.serial_edit.text().strip() or cfg.serial_number
        cfg.acq_mode = self.mode_combo.currentText()
        cfg.trigger_channel = self.trig_ch_combo.currentText()
        cfg.trigger_level_v = self.trig_level_spin.value()
        cfg.trigger_slope = self.trig_slope_combo.currentText()
        cfg.sampling_rate_hz = self._rate_values[self.rate_combo.currentIndex()]
        cfg.start_time_s = self.start_spin.value() * 1e-3
        cfg.stop_time_s = self.stop_spin.value() * 1e-3
        for i in range(4):
            cfg.enabled[i] = self.ch_enable[i].isChecked()
            cfg.ranges[i] = (self.ch_min[i].value(), self.ch_max[i].value())
            cfg.couplings[i] = self.ch_coupling[i].currentText()

    def _on_config_changed(self, *args):
        if getattr(self, "_loading", False):
            return
        self._read_config_from_controls()
        self.controller.mark_dirty()
        self._update_nsamp_label()
        for i in range(4):
            if not self.controller.config.enabled[i]:
                self.curves[i].setData([], [])

    def _update_nsamp_label(self):
        self.nsamp_lbl.setText(f"N = {self.controller.config.num_samples:,} samples")

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

    def _on_mode_changed(self, idx):
        """Swap the active analysis mode: tear down the old one, set up the new."""
        self.active_mode.deactivate()
        self.mode_stack.setCurrentIndex(idx)
        self.active_mode = self.modes[idx]
        self.active_mode.activate()
        self._set_running_state(self.worker is not None and self.worker.isRunning())

    # mode panels call these public helpers
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
        self.worker = AcquisitionWorker(self.controller, continuous=continuous)
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
        t, channels, metrics = payload
        self.active_mode.on_frame(t, channels, metrics)

    def decimate_display(self, t, y):
        """Stride-decimate one trace to <= MAX_DISPLAY_POINTS for fast drawing.

        Display-only: returns a view of every step-th sample (step chosen so the
        result never exceeds the cap). Short traces pass through unchanged."""
        n = len(t)
        if n <= self.MAX_DISPLAY_POINTS:
            return t, y
        step = int(np.ceil(n / self.MAX_DISPLAY_POINTS))
        return t[::step], y[::step]

    def save_full(self):
        """Save the full-resolution last capture."""
        self._save_capture(decimated=False)

    def save_display(self):
        """Save the decimated trace as displayed (<= MAX_DISPLAY_POINTS points)."""
        self._save_capture(decimated=True)

    def _save_capture(self, decimated):
        cap = self.controller.last_capture
        if cap is None:
            QtWidgets.QMessageBox.information(self, "Save", "No capture to save yet.")
            return
        t, channels = cap
        if decimated:
            # one shared stride (all channels share t), reusing the draw-path helper
            t = self.decimate_display(t, t)[0]
            channels = [self.decimate_display(cap[0], c)[1] for c in channels]
            default, label = "capture_display.npz", "display waveform"
        else:
            default, label = "capture_full.npz", "full waveform"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, f"Save {label}", default, "NumPy archive (*.npz)")
        if not path:
            return
        np.savez(path, t=t, A=channels[0], B=channels[1], C=channels[2], D=channels[3])
        self.status_lbl.setText(f"Saved {label}: {path}")

    def autoscale_x(self):
        """Fit the x-axis to the full time span of the last frame."""
        cap = self.controller.last_capture
        if cap is None or len(cap[0]) == 0:
            return
        t = cap[0]
        self.plot.setXRange(float(t[0]), float(t[-1]), padding=0)

    def autoscale_y(self):
        """Fit the y-axis to the measured min/max across enabled channels."""
        cap = self.controller.last_capture
        if cap is None:
            return
        _, channels = cap
        ys = [channels[i] for i in range(4)
              if self.controller.config.enabled[i] and len(channels[i])]
        if not ys:
            return
        ymin = min(float(np.min(y)) for y in ys)
        ymax = max(float(np.max(y)) for y in ys)
        if ymin == ymax:
            pad = abs(ymin) * 0.1 or 0.5
            ymin, ymax = ymin - pad, ymax + pad
        self.plot.setYRange(ymin, ymax, padding=0.05)

    def show_fft_panel(self, visible):
        """Reveal/hide the bottom FFT pane (waveform ~2/3, FFT ~1/3 when shown)."""
        self.fft_plot.setVisible(visible)
        if visible:
            h = self.plot_splitter.height() or self.height()
            self.plot_splitter.setSizes([int(h * 2 / 3), int(h / 3)])

    def _set_running_state(self, running):
        # `continuous` is tracked on the window (set when a run starts) so it stays
        # correct across mode switches and worker callbacks — otherwise switching
        # modes mid-run would drop the flag and gray out Stop with no way back.
        if not running:
            self._continuous = False
        self.connect_btn.setEnabled(not running)
        self.active_mode.set_running_state(running, self._continuous)

    @staticmethod
    def fmt_hz(hz):
        if not np.isfinite(hz):
            return "-"
        for div, unit in [(1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")]:
            if abs(hz) >= div:
                return f"{hz/div:g} {unit}"
        return f"{hz:g} Hz"

    def closeEvent(self, event):
        self.stop_acquisition()
        if self.controller.connected:
            self.controller.disconnect()
        super().closeEvent(event)


def main(simulate=False):
    if "--simulate" in sys.argv or "-s" in sys.argv:
        simulate = True
    app = QtWidgets.QApplication(sys.argv)
    win = ScopeWindow(simulate=simulate)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

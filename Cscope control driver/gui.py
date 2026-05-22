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

from controller import (ScopeController, ScopeConfig, CH_NAMES, CH_COLORS,
                        ACQ_MODES)


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
    def __init__(self, simulate=False):
        super().__init__()
        self.setWindowTitle("Cleverscope Readout" + (" [SIMULATION]" if simulate else ""))
        self.resize(1100, 650)

        self.controller = ScopeController(simulate=simulate)
        self.worker = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        layout.addWidget(self._build_controls(), 0)
        layout.addWidget(self._build_plot(), 1)

        self._set_running_state(False)
        self._sync_controls_to_config()

    # ---------- UI construction ----------
    def _build_controls(self):
        panel = QtWidgets.QWidget()
        panel.setFixedWidth(330)
        v = QtWidgets.QVBoxLayout(panel)

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

        # run controls
        run_box = QtWidgets.QGroupBox("Run")
        rg = QtWidgets.QGridLayout(run_box)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(ACQ_MODES)
        self.mode_combo.currentTextChanged.connect(self._on_config_changed)
        self.run_btn = QtWidgets.QPushButton("Run")
        self.run_btn.clicked.connect(self._start_continuous)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop_acquisition)
        self.single_btn = QtWidgets.QPushButton("Single")
        self.single_btn.clicked.connect(self._start_single)
        rg.addWidget(QtWidgets.QLabel("Mode"), 0, 0)
        rg.addWidget(self.mode_combo, 0, 1, 1, 2)
        rg.addWidget(self.run_btn, 1, 0)
        rg.addWidget(self.stop_btn, 1, 1)
        rg.addWidget(self.single_btn, 1, 2)
        v.addWidget(run_box)

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
        self._rate_values = [400e6, 200e6, 100e6, 50e6, 20e6, 10e6, 1e6]
        self.rate_combo.addItems([self._fmt_hz(r) for r in self._rate_values])
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

        # display autoscale
        disp_box = QtWidgets.QGroupBox("Display")
        dg = QtWidgets.QHBoxLayout(disp_box)
        self.autox_btn = QtWidgets.QPushButton("Auto X (full range)")
        self.autox_btn.clicked.connect(self._autoscale_x)
        self.autoy_btn = QtWidgets.QPushButton("Auto Y (measured)")
        self.autoy_btn.clicked.connect(self._autoscale_y)
        dg.addWidget(self.autox_btn)
        dg.addWidget(self.autoy_btn)
        v.addWidget(disp_box)

        self.save_btn = QtWidgets.QPushButton("Save last frame (.npz)")
        self.save_btn.clicked.connect(self._save_last)
        v.addWidget(self.save_btn)

        self.metrics_lbl = QtWidgets.QLabel("No data yet.")
        self.metrics_lbl.setWordWrap(True)
        v.addWidget(self.metrics_lbl)
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
        return self.plot

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
            self._stop_acquisition()
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

    def _start_continuous(self):
        self._start_worker(continuous=True)

    def _start_single(self):
        self._start_worker(continuous=False)

    def _start_worker(self, continuous):
        if not self.controller.connected:
            QtWidgets.QMessageBox.information(self, "Not connected", "Connect to the scope first.")
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self._read_config_from_controls()
        self.worker = AcquisitionWorker(self.controller, continuous=continuous)
        self.worker.frameReady.connect(self._on_frame)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_done)
        self._set_running_state(True, continuous=continuous)
        self.worker.start()

    def _stop_acquisition(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(2000)

    def _on_worker_done(self):
        self._set_running_state(False)

    def _on_failed(self, msg):
        self.status_lbl.setText(msg)

    def _on_frame(self, payload):
        t, channels, metrics = payload
        for i in range(4):
            if self.controller.config.enabled[i]:
                self.curves[i].setData(t, channels[i])
            else:
                self.curves[i].setData([], [])
        self.metrics_lbl.setText(
            f"N = {metrics['n']:,}   fs = {self._fmt_hz(metrics['fs'])}\n"
            f"dt = {metrics['dt']*1e9:.2f} ns   span = {metrics['duration']*1e3:.3f} ms")

    def _save_last(self):
        cap = self.controller.last_capture
        if cap is None:
            QtWidgets.QMessageBox.information(self, "Save", "No capture to save yet.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save last frame", "capture.npz", "NumPy archive (*.npz)")
        if not path:
            return
        t, channels = cap
        np.savez(path, t=t, A=channels[0], B=channels[1], C=channels[2], D=channels[3])
        self.status_lbl.setText(f"Saved {path}")

    def _autoscale_x(self):
        """Fit the x-axis to the full time span of the last frame."""
        cap = self.controller.last_capture
        if cap is None or len(cap[0]) == 0:
            return
        t = cap[0]
        self.plot.setXRange(float(t[0]), float(t[-1]), padding=0)

    def _autoscale_y(self):
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

    def _set_running_state(self, running, continuous=False):
        connected = self.controller.connected
        self.run_btn.setEnabled(connected and not running)
        self.single_btn.setEnabled(connected and not running)
        self.stop_btn.setEnabled(running and continuous)
        self.connect_btn.setEnabled(not running)

    @staticmethod
    def _fmt_hz(hz):
        if not np.isfinite(hz):
            return "-"
        for div, unit in [(1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")]:
            if abs(hz) >= div:
                return f"{hz/div:g} {unit}"
        return f"{hz:g} Hz"

    def closeEvent(self, event):
        self._stop_acquisition()
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

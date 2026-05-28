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

    The 'normal' (non-hovered) color is per-instance so it can be re-tinted to
    a channel color via set_normal_color(); the Y axes use this to follow
    whichever channel on their side was most recently programmed."""

    HOVER = (0, 0, 0)

    def __init__(self, orientation, **kwargs):
        super().__init__(orientation, **kwargs)
        self.setAcceptHoverEvents(True)
        self._normal_color = (120, 120, 120)
        self._apply(self._normal_color, 1)

    def _apply(self, color, width):
        self.setPen(pg.mkPen(color, width=width))
        self.setTextPen(pg.mkPen(color))

    def set_normal_color(self, color):
        """Set the color the axis returns to after a hover-leave."""
        self._normal_color = color
        self._apply(self._normal_color, 1)

    def hoverEnterEvent(self, event):
        self._apply(self.HOVER, 2)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._apply(self._normal_color, 1)
        super().hoverLeaveEvent(event)


class ButtonCluster(QtWidgets.QWidget):
    """Compact 5-button pad — pan-, zoom out, reset, zoom in, pan+.

    Drives a *programmed* axis range (time or per-channel voltage). Mouse pan/
    zoom on the plot stays display-only; only these buttons move the underlying
    config. With show_readout=True a small numeric label is shown between the
    two pan buttons (used for non-embedded callers); embedded-on-plot clusters
    pass show_readout=False so the data area stays clean — the axis ticks
    already display the programmed range.

    orientation: "h" for time-axis (pan labels '<' '>'), "v" for voltage ('v' '^').
    color:       optional CSS color tinting border + text to match a channel.
    """

    zoomIn = QtCore.Signal()
    zoomOut = QtCore.Signal()
    panNeg = QtCore.Signal()
    panPos = QtCore.Signal()
    reset = QtCore.Signal()

    def __init__(self, orientation="h", color=None, show_readout=True, parent=None):
        super().__init__(parent)
        if orientation == "v":
            pan_neg_lbl, pan_pos_lbl = "v", "^"
            # Wiring inverts the sign so 'v' visually moves the signal down.
            pan_neg_tip, pan_pos_tip = "Pan signal down by 1/4 span", "Pan signal up by 1/4 span"
        else:
            pan_neg_lbl, pan_pos_lbl = "<", ">"
            pan_neg_tip, pan_pos_tip = "Pan signal left by 1/4 span", "Pan signal right by 1/4 span"

        style = ""
        if color is not None:
            style = (f"QToolButton {{ border: 2px solid {color}; color: {color}; "
                     f"font-weight: bold; border-radius: 3px; "
                     f"background: rgba(255,255,255,200); }} "
                     f"QToolButton:pressed {{ background: {color}; color: white; }}")

        def mkbtn(text, tip, signal):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setFixedSize(24, 22)
            b.setAutoRaise(False)
            if style:
                b.setStyleSheet(style)
            b.clicked.connect(signal.emit)
            return b

        self._btn_zoom_out = mkbtn("-", "Zoom out 1.5x", self.zoomOut)
        self._btn_zoom_in = mkbtn("+", "Zoom in 1.5x", self.zoomIn)
        self._btn_reset = mkbtn("R", "Reset to default", self.reset)
        self._btn_pan_neg = mkbtn(pan_neg_lbl, pan_neg_tip, self.panNeg)
        self._btn_pan_pos = mkbtn(pan_pos_lbl, pan_pos_tip, self.panPos)

        self._show_readout = show_readout
        if show_readout:
            self._readout = QtWidgets.QLabel("")
            self._readout.setAlignment(QtCore.Qt.AlignCenter)
            if color is not None:
                self._readout.setStyleSheet(f"color: {color}; font-weight: bold;")
            g = QtWidgets.QGridLayout(self)
            g.setContentsMargins(0, 0, 0, 0)
            g.setHorizontalSpacing(3)
            g.setVerticalSpacing(2)
            g.addWidget(self._btn_zoom_out, 0, 0)
            g.addWidget(self._btn_zoom_in, 0, 1)
            g.addWidget(self._btn_reset, 0, 2)
            g.addWidget(self._btn_pan_neg, 1, 0)
            g.addWidget(self._readout, 1, 1)
            g.addWidget(self._btn_pan_pos, 1, 2)
        else:
            self._readout = None
            # Compact 5-button strip, oriented to match the axis the cluster
            # serves. Voltage ('v' orientation) stacks vertically so '^' sits
            # at the top and 'v' at the bottom — pan buttons map to actual
            # screen direction. Time ('h' orientation) stays horizontal so
            # '<' is on the left and '>' on the right under the time axis.
            if orientation == "v":
                lay = QtWidgets.QVBoxLayout(self)
                order = [self._btn_pan_pos, self._btn_zoom_in,
                         self._btn_reset,
                         self._btn_zoom_out, self._btn_pan_neg]
            else:
                lay = QtWidgets.QHBoxLayout(self)
                order = [self._btn_pan_neg, self._btn_zoom_out,
                         self._btn_reset,
                         self._btn_zoom_in, self._btn_pan_pos]
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(3)
            for w in order:
                lay.addWidget(w)

    def set_readout(self, text):
        if self._readout is not None:
            self._readout.setText(text)


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
        # Snapshot the startup config so Reset buttons can restore start/stop and
        # per-channel ranges to where they began (instead of hard-coded constants).
        self._config_defaults = self.controller.config.copy()
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

        # time base — rate + sample count only; the zoom/pan/reset cluster lives
        # on the plot itself (see _build_plot_overlays).
        tb_box = QtWidgets.QGroupBox("Time base")
        bg = QtWidgets.QGridLayout(tb_box)
        self.rate_combo = QtWidgets.QComboBox()
        self._rate_values = [400e6, 200e6, 100e6, 50e6, 20e6, 10e6, 1e6,
                             400e3, 200e3, 100e3]
        self.rate_combo.addItems([self.fmt_hz(r) for r in self._rate_values])
        self.rate_combo.currentIndexChanged.connect(self._on_config_changed)
        self.nsamp_lbl = QtWidgets.QLabel("")
        bg.addWidget(QtWidgets.QLabel("Rate"), 0, 0)
        bg.addWidget(self.rate_combo, 0, 1)
        bg.addWidget(self.nsamp_lbl, 1, 0, 1, 2)
        v.addWidget(tb_box)

        # channels — enable + coupling. Per-channel range is set with the
        # color-coded button cluster overlaid at the matching plot corner
        # (A top-left, B bottom-left, C top-right, D bottom-right).
        ch_box = QtWidgets.QGroupBox("Channels")
        cg2 = QtWidgets.QGridLayout(ch_box)
        cg2.addWidget(QtWidgets.QLabel("On"), 0, 0)
        cg2.addWidget(QtWidgets.QLabel("Ch"), 0, 1)
        cg2.addWidget(QtWidgets.QLabel("Cpl"), 0, 2)
        self.ch_enable = []
        self.ch_coupling = []
        for i, name in enumerate(CH_NAMES):
            en = QtWidgets.QCheckBox()
            en.toggled.connect(self._on_config_changed)
            lbl = QtWidgets.QLabel(name)
            lbl.setStyleSheet(f"color: {CH_COLORS[i]}; font-weight: bold;")
            cpl = QtWidgets.QComboBox(); cpl.addItems(["AC", "DC"])
            cpl.currentTextChanged.connect(self._on_config_changed)
            row = i + 1
            cg2.addWidget(en, row, 0)
            cg2.addWidget(lbl, row, 1)
            cg2.addWidget(cpl, row, 2)
            self.ch_enable.append(en)
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
                                             "left": HoverAxis("left"),
                                             "right": HoverAxis("right")})
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "Time", units="s")
        # Axis labels start as their primary channel (left → A, right → C) and
        # follow whichever channel on that side was pressed last (see _tint_axis).
        self.plot.setLabel("left", "Voltage A", units="V")
        self.plot.setLabel("right", "Voltage C", units="V")
        self.plot.showAxis("right")
        self.plot.addLegend()

        # One ViewBox per channel, all stacked in the same on-screen rectangle
        # and X-linked, so each channel has a fully independent Y range —
        # zooming A no longer drags B's display along with it. The left axis is
        # re-linked between A and B (and the right between C and D) by
        # _tint_axis whenever the user presses that channel's cluster.
        vb_a = self.plot.getViewBox()        # main; A
        vb_b = pg.ViewBox()
        vb_c = pg.ViewBox()
        vb_d = pg.ViewBox()
        self._vb = [vb_a, vb_b, vb_c, vb_d]
        for vb in (vb_b, vb_c, vb_d):
            self.plot.scene().addItem(vb)
            vb.setXLink(vb_a)
        self.plot.getAxis("left").linkToView(vb_a)   # A on left initially
        self.plot.getAxis("right").linkToView(vb_c)  # C on right initially

        def _sync_views():
            rect = vb_a.sceneBoundingRect()
            for vb in (vb_b, vb_c, vb_d):
                vb.setGeometry(rect)
                vb.linkedViewChanged(vb_a, vb.XAxis)
        vb_a.sigResized.connect(_sync_views)
        self._sync_views = _sync_views

        self.curves = []
        for i, name in enumerate(CH_NAMES):
            curve = pg.PlotDataItem(pen=pg.mkPen(CH_COLORS[i], width=1),
                                    name=f"Ch {name}")
            curve.setDownsampling(auto=True)
            curve.setClipToView(True)
            self._vb[i].addItem(curve)
            if i != 0:
                # Only items in the main VB auto-register; register the rest.
                self.plot.plotItem.legend.addItem(curve, f"Ch {name}")
            self.curves.append(curve)
        _sync_views()

        # Build the corner channel clusters as children of self.plot, and the
        # time cluster as a centered row directly under the plot.
        self._build_plot_overlays()

        # Wrap the plot + time-row in one widget so the splitter sees them as
        # a single pane (the FFT pane is the splitter's other half).
        plot_pane = QtWidgets.QWidget()
        pp = QtWidgets.QVBoxLayout(plot_pane)
        pp.setContentsMargins(0, 0, 0, 0)
        pp.setSpacing(2)
        pp.addWidget(self.plot, 1)
        time_row = QtWidgets.QWidget()
        tr = QtWidgets.QHBoxLayout(time_row)
        tr.setContentsMargins(0, 0, 0, 4)
        tr.addStretch(1)
        tr.addWidget(self.time_cluster)
        tr.addStretch(1)
        pp.addWidget(time_row, 0)

        # FFT plot lives in the bottom pane, hidden until FFT View mode reveals it.
        self.fft_plot = pg.PlotWidget(axisItems={"bottom": HoverAxis("bottom"),
                                                 "left": HoverAxis("left")})
        self.fft_plot.setBackground("w")
        self.fft_plot.showGrid(x=True, y=True, alpha=0.3)
        self.fft_plot.setLabel("bottom", "Frequency", units="Hz")
        self.fft_plot.setLabel("left", "Magnitude")
        self.fft_plot.hide()

        self.plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.plot_splitter.addWidget(plot_pane)
        self.plot_splitter.addWidget(self.fft_plot)
        return self.plot_splitter

    def _build_plot_overlays(self):
        """Create the five button clusters and pin the four channel ones to the
        plot corners. The time cluster is placed into a centered row by the
        caller; here we only construct it.

        Pan-direction wiring is inverted on purpose: the user thinks of the
        signal moving, not the range. Clicking 'v' should make the trace
        appear lower on screen, which means the displayed range shifts up
        (frac > 0). Same for '<' on time."""
        self.ch_cluster = []
        for i in range(4):
            cl = ButtonCluster("v", color=CH_COLORS[i], show_readout=False,
                               parent=self.plot)
            cl.zoomIn.connect(lambda _ch=i: self._volt_zoom(_ch, 1.0 / 1.5))
            cl.zoomOut.connect(lambda _ch=i: self._volt_zoom(_ch, 1.5))
            cl.panNeg.connect(lambda _ch=i: self._volt_pan(_ch, +0.25))  # signal down → range up
            cl.panPos.connect(lambda _ch=i: self._volt_pan(_ch, -0.25))  # signal up   → range down
            cl.reset.connect(lambda _ch=i: self._volt_reset(_ch))
            cl.raise_()
            self.ch_cluster.append(cl)

        self.time_cluster = ButtonCluster("h", show_readout=False)
        self.time_cluster.zoomIn.connect(lambda: self._time_zoom(1.0 / 1.5))
        self.time_cluster.zoomOut.connect(lambda: self._time_zoom(1.5))
        self.time_cluster.panNeg.connect(lambda: self._time_pan(+0.25))  # signal left  → range later
        self.time_cluster.panPos.connect(lambda: self._time_pan(-0.25))  # signal right → range earlier
        self.time_cluster.reset.connect(self._time_reset)

        # Reposition the corner clusters whenever the plot widget resizes.
        self.plot.installEventFilter(self)
        self._reposition_overlays()

    def _reposition_overlays(self):
        """Pin A,B,C,D clusters to plot corners with a small inward pad."""
        if not hasattr(self, "ch_cluster") or not self.ch_cluster:
            return
        pad = 6
        w, h = self.plot.width(), self.plot.height()
        for cl in self.ch_cluster:
            cl.adjustSize()
        a, b, c, d = self.ch_cluster
        a.move(pad, pad)                                   # A: top-left
        b.move(pad, h - b.height() - pad)                  # B: bottom-left
        c.move(w - c.width() - pad, pad)                   # C: top-right
        d.move(w - d.width() - pad, h - d.height() - pad)  # D: bottom-right
        for cl in self.ch_cluster:
            cl.raise_()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "plot", None) and event.type() == QtCore.QEvent.Resize:
            self._reposition_overlays()
        return super().eventFilter(obj, event)

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
        for i in range(4):
            self.ch_enable[i].setChecked(cfg.enabled[i])
            self.ch_coupling[i].setCurrentText(cfg.couplings[i])
        self._loading = False
        self._refresh_cluster_readouts()
        self._update_nsamp_label()
        # Snap every per-channel ViewBox to its programmed Y range, plus the
        # shared X axis to the programmed time window.
        self.plot.setXRange(cfg.start_time_s, cfg.stop_time_s, padding=0)
        for i in range(4):
            self._vb[i].setYRange(*cfg.ranges[i], padding=0)
        # Color/link the left axis to A and the right axis to C as the startup
        # default so the tick labels are meaningful on first frame.
        self._tint_axis(0)
        self._tint_axis(2)

    def _read_config_from_controls(self):
        cfg = self.controller.config
        cfg.serial_number = self.serial_edit.text().strip() or cfg.serial_number
        cfg.acq_mode = self.mode_combo.currentText()
        cfg.trigger_channel = self.trig_ch_combo.currentText()
        cfg.trigger_level_v = self.trig_level_spin.value()
        cfg.trigger_slope = self.trig_slope_combo.currentText()
        cfg.sampling_rate_hz = self._rate_values[self.rate_combo.currentIndex()]
        for i in range(4):
            cfg.enabled[i] = self.ch_enable[i].isChecked()
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

    # ---------- programmed-axis (button) controls ----------
    @staticmethod
    def _zoom_bounds(lo, hi, factor):
        c = (lo + hi) / 2.0
        new = (hi - lo) * factor / 2.0
        return c - new, c + new

    @staticmethod
    def _pan_bounds(lo, hi, frac):
        shift = (hi - lo) * frac
        return lo + shift, hi + shift

    def _time_zoom(self, factor):
        cfg = self.controller.config
        cfg.start_time_s, cfg.stop_time_s = self._zoom_bounds(
            cfg.start_time_s, cfg.stop_time_s, factor)
        self._commit_time()

    def _time_pan(self, frac):
        cfg = self.controller.config
        cfg.start_time_s, cfg.stop_time_s = self._pan_bounds(
            cfg.start_time_s, cfg.stop_time_s, frac)
        self._commit_time()

    def _time_reset(self):
        cfg = self.controller.config
        cfg.start_time_s = self._config_defaults.start_time_s
        cfg.stop_time_s = self._config_defaults.stop_time_s
        self._commit_time()

    def _volt_zoom(self, ch, factor):
        cfg = self.controller.config
        lo, hi = cfg.ranges[ch]
        cfg.ranges[ch] = self._zoom_bounds(lo, hi, factor)
        self._commit_volt(ch)

    def _volt_pan(self, ch, frac):
        cfg = self.controller.config
        lo, hi = cfg.ranges[ch]
        cfg.ranges[ch] = self._pan_bounds(lo, hi, frac)
        self._commit_volt(ch)

    def _volt_reset(self, ch):
        cfg = self.controller.config
        cfg.ranges[ch] = tuple(self._config_defaults.ranges[ch])
        self._commit_volt(ch)

    def _commit_time(self):
        """Clamp time bounds, push to hardware, snap display X, update readout."""
        cfg = self.controller.config
        lo, hi = cfg.start_time_s, cfg.stop_time_s
        # clamp endpoints to the old spinbox range (1 s either side)
        lo = max(-1.0, min(1.0, lo))
        hi = max(-1.0, min(1.0, hi))
        # enforce at least 2 samples worth of duration
        min_span = 2.0 / max(cfg.sampling_rate_hz, 1.0)
        if hi - lo < min_span:
            c = (lo + hi) / 2.0
            lo, hi = c - min_span / 2.0, c + min_span / 2.0
        cfg.start_time_s, cfg.stop_time_s = lo, hi
        self.controller.mark_dirty()
        self.plot.setXRange(lo, hi, padding=0)
        self._update_nsamp_label()
        self._refresh_cluster_readouts()

    def _commit_volt(self, ch):
        """Clamp voltage bounds, push to hardware, snap only this channel's VB."""
        cfg = self.controller.config
        lo, hi = cfg.ranges[ch]
        lo = max(-100.0, min(100.0, lo))
        hi = max(-100.0, min(100.0, hi))
        if hi - lo < 1e-3:
            c = (lo + hi) / 2.0
            lo, hi = c - 5e-4, c + 5e-4
        cfg.ranges[ch] = (lo, hi)
        self.controller.mark_dirty()
        # Only this channel's ViewBox moves — the other channel on the same
        # axis side keeps its own programmed range untouched.
        self._vb[ch].setYRange(lo, hi, padding=0)
        self._tint_axis(ch)
        self._refresh_cluster_readouts()

    def _tint_axis(self, ch):
        """Re-link the appropriate axis to ch's ViewBox, color it the channel's
        pen color, and relabel it 'Voltage <name>' so the tick scale always
        belongs to a single named channel."""
        side = "left" if ch < 2 else "right"
        axis = self.plot.getAxis(side)
        axis.linkToView(self._vb[ch])
        # pyqtgraph's linkToView only connects signals — it does not push the
        # newly-linked view's current range. Without this manual sync, the
        # tick labels stay frozen on the previous channel's range until the
        # next range change fires.
        axis.linkedViewChanged(self._vb[ch])
        if isinstance(axis, HoverAxis):
            axis.set_normal_color(CH_COLORS[ch])
        self.plot.setLabel(side, f"Voltage {CH_NAMES[ch]}", units="V")

    def _viewbox_for(self, ch):
        """Each channel has its own ViewBox so ranges are fully independent."""
        return self._vb[ch]

    def _add_overlay(self, item, ch):
        """Add an overlay item (e.g. a fit curve) to the right channel's VB."""
        self._viewbox_for(ch).addItem(item)

    def _refresh_cluster_readouts(self):
        cfg = self.controller.config
        span_ms_lo = cfg.start_time_s * 1e3
        span_ms_hi = cfg.stop_time_s * 1e3
        self.time_cluster.set_readout(f"{span_ms_lo:+.3g} – {span_ms_hi:+.3g} ms")
        for i in range(4):
            lo, hi = cfg.ranges[i]
            if abs(lo + hi) < 1e-9 and hi > 0:
                txt = f"±{hi:.3g} V"
            else:
                txt = f"{lo:.3g} / {hi:.3g} V"
            self.ch_cluster[i].set_readout(txt)

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
        """Fit each channel's ViewBox to that channel's own min/max — fully
        independent now that A/B/C/D each own a ViewBox."""
        cap = self.controller.last_capture
        if cap is None:
            return
        _, channels = cap
        cfg = self.controller.config
        for i in range(4):
            y = channels[i]
            if not cfg.enabled[i] or len(y) == 0:
                continue
            ymin, ymax = float(np.min(y)), float(np.max(y))
            if ymin == ymax:
                pad = abs(ymin) * 0.1 or 0.5
                ymin, ymax = ymin - pad, ymax + pad
            self._vb[i].setYRange(ymin, ymax, padding=0.05)

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

"""Hardware-agnostic control layer for the Cleverscope readout app.

`ScopeController` wraps either the real `CScope` (cscope_class.py) or `MockScope`
(synthetic noisy sine waves) behind one interface, so the GUI and any analysis
notebook drive the scope the same way:

    c = ScopeController(simulate=True)
    c.connect()
    c.apply_config(c.config)
    t, channels, metrics = c.acquire_once("Triggered")

Vendor modules (CleverscopeInterface, cscope_class, the T_* specs) are imported
lazily inside the real path so simulate mode needs nothing but numpy.
"""

from dataclasses import dataclass, field, replace
import numpy as np

CH_NAMES = ["A", "B", "C", "D"]
CH_COLORS = ["red", "blue", "green", "orange"]
ACQ_MODES = ["Auto", "Triggered", "Single"]


@dataclass
class ScopeConfig:
    """Everything the GUI can edit. Plain values, no ctypes / vendor enums."""
    serial_number: str = "EQ10014"
    sampling_rate_hz: float = 100e6
    start_time_s: float = -0.5e-3
    stop_time_s: float = 6.5e-3
    ranges: list = field(default_factory=lambda: [(-0.5, 0.5), (-0.2, 0.2), (-1.0, 1.0), (-5.0, 5.0)])
    couplings: list = field(default_factory=lambda: ["AC", "AC", "AC", "DC"])
    enabled: list = field(default_factory=lambda: [True, True, True, True])
    trigger_channel: str = "D"
    trigger_level_v: float = 1.0
    trigger_slope: str = "Rising"
    acq_mode: str = "Auto"

    def copy(self):
        return replace(self,
                       ranges=list(self.ranges),
                       couplings=list(self.couplings),
                       enabled=list(self.enabled))

    @property
    def num_samples(self):
        duration = self.stop_time_s - self.start_time_s
        return max(1, int(duration * self.sampling_rate_hz))


def acquisition_metrics(t):
    """Package the dt/fs/N/duration block the notebook recomputes by hand."""
    n = len(t)
    if n < 2:
        return {"n": n, "dt": float("nan"), "fs": float("nan"), "duration": 0.0}
    dt = float(t[1] - t[0])
    return {"n": n, "dt": dt, "fs": 1.0 / dt, "duration": float(t[-1] - t[0])}


class MockScope:
    """Drop-in stand-in for `CScope`: same methods the controller calls, but it
    synthesizes noisy sine waves so the whole app runs with no DLL or hardware."""

    MAX_DISPLAY_SAMPLES = 200_000  # keep synthetic frames light for a smooth live loop

    def __init__(self):
        self.start = -0.5e-3
        self.stop = 6.5e-3
        self.rate = 100e6
        self.ranges = [(-0.5, 0.5), (-0.2, 0.2), (-1.0, 1.0), (-5.0, 5.0)]
        self.trig_ch = "D"
        self.trig_level = 1.0
        self.trig_slope = "Rising"
        self._connected = False
        self._rng = np.random.default_rng()
        # per-channel synthetic tone frequencies (Hz)
        self._freqs = [2.5e6, 3.6e6, 1.0e6, 1.0e3]

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
        self.trig_ch, self.trig_level, self.trig_slope = trig_ch, TriggerLevel, TriggerType
        return True

    def set_ch_range(self, ChannelIndex, MinVolts, MaxVolts):
        self.ranges[ChannelIndex] = (MinVolts, MaxVolts)
        return True

    def set_ch_coupling(self, ChannelIndex, coupling):
        return True

    def get_single_acquisition(self, acq_type=None, timeout=10.0):
        duration = self.stop - self.start
        n_full = max(2, int(duration * self.rate))
        n = min(n_full, self.MAX_DISPLAY_SAMPLES)
        t = np.linspace(self.start, self.stop, n)

        channels = []
        for i in range(4):
            lo, hi = self.ranges[i]
            amp = 0.4 * (hi - lo) / 2.0
            f = self._freqs[i]
            if i == 3:
                # channel D: a TTL-ish square (trigger reference)
                sig = np.where(np.sin(2 * np.pi * f * t) >= 0, hi * 0.8, lo * 0.1)
            else:
                phase = self._rng.uniform(0, 2 * np.pi)
                sig = amp * np.sin(2 * np.pi * f * t + phase)
            noise = self._rng.normal(0.0, 0.04 * (hi - lo) / 2.0, size=n)
            channels.append(np.clip(sig + noise, lo, hi))

        return [t, tuple(channels)]


class ScopeController:
    """Thin orchestration layer over CScope / MockScope.

    Tracks a single `ScopeConfig`, applies it to the hardware in one call, and
    exposes `acquire_once`. The GUI worker thread calls `apply_config` /
    `acquire_once`; the GUI thread only edits `config` and reads `last_capture`.
    """

    def __init__(self, simulate=False, config=None):
        self.simulate = simulate
        self.config = config or ScopeConfig()
        self._scope = None
        self._dirty = True
        self.last_capture = None  # (t, channels) of the most recent frame

    @property
    def connected(self):
        return self._scope is not None and self._scope.IsConnected()

    def mark_dirty(self):
        self._dirty = True

    def needs_apply(self):
        return self._dirty

    def connect(self):
        cfg = self.config
        if self.simulate:
            self._scope = MockScope()
        else:
            # vendor + DLL only touched on the real path
            import cscope_class
            from T_AcquireSpec import T_TrigChannel
            trig_map = {
                "A": T_TrigChannel.T_TrigChan_ChanA,
                "B": T_TrigChannel.T_TrigChan_ChanB,
                "C": T_TrigChannel.T_TrigChan_ChanC,
                "D": T_TrigChannel.T_TrigChan_ChanD,
            }
            self._scope = cscope_class.CScope()
            ok = self._scope.connect(
                serial_number=cfg.serial_number,
                start_time_s=cfg.start_time_s,
                stop_time_s=cfg.stop_time_s,
                trigger_level_v=cfg.trigger_level_v,
                trigger_channel=trig_map.get(cfg.trigger_channel, T_TrigChannel.T_TrigChan_ChanD),
                probe_range_v=cfg.ranges[0],
                sampling_rate_hz=cfg.sampling_rate_hz,
            )
            if not ok:
                self._scope = None
                return False

        if self.simulate:
            self._scope.connect(
                start_time_s=cfg.start_time_s,
                stop_time_s=cfg.stop_time_s,
                sampling_rate_hz=cfg.sampling_rate_hz,
            )
        self._dirty = True
        return self.connected

    def disconnect(self):
        if self._scope is not None:
            self._scope.disconnect()
        self._scope = None

    def apply_config(self, config=None):
        """Push the full config to the scope in one call (replaces the notebook's
        per-channel config loops + separate time/trigger updates)."""
        if config is not None:
            self.config = config
        if self._scope is None:
            return False
        cfg = self.config
        for i in range(4):
            lo, hi = cfg.ranges[i]
            self._scope.set_ch_range(i, lo, hi)
            self._scope.set_ch_coupling(i, cfg.couplings[i])
        self._scope.update_time_axis(cfg.start_time_s, cfg.stop_time_s, cfg.sampling_rate_hz)
        self._scope.update_trigger(cfg.trigger_channel, cfg.trigger_level_v, cfg.trigger_slope)
        self._dirty = False
        return True

    def _mode_arg(self, mode):
        if self.simulate:
            return mode
        from T_AcquireSpec import T_AcquireAction
        return {
            "Auto": T_AcquireAction.T_AcquireAction_Automatic,
            "Triggered": T_AcquireAction.T_AcquireAction_Triggered,
            "Single": T_AcquireAction.T_AcquireAction_Single,
        }[mode]

    def acquire_once(self, mode=None, timeout=10.0):
        """Capture one frame. Returns (t, channels, metrics) or (None, None, None)."""
        if self._scope is None:
            return None, None, None
        mode = mode or self.config.acq_mode
        result = self._scope.get_single_acquisition(self._mode_arg(mode), timeout)
        if not result or result[0] is None:
            return None, None, None
        t, channels = result
        self.last_capture = (t, channels)
        return t, channels, acquisition_metrics(t)

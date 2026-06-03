"""Pure-numpy/scipy analysis routines for the readout app.

No Qt here on purpose: these functions are the math behind the GUI's analysis
modes and are meant to be imported and reused from a Jupyter notebook the same
way the GUI uses them, e.g.

    from analysis import fit_lorentzian
    res = fit_lorentzian(t, channels[2])
    if res["success"]:
        print(res["params"]["fwhm"], res["r2"])
"""

import numpy as np
from scipy.optimize import curve_fit
from scipy.signal import find_peaks


def lorentzian(t, t0, fwhm, amp, offset):
    """Lorentzian lineshape vs. the sweep/time axis.

    `amp` is the signed peak height above `offset` (positive => peak, negative
    => dip); `fwhm` is the full width at half maximum in the units of `t`.
    """
    hwhm = fwhm / 2.0
    return offset + amp * hwhm**2 / ((t - t0)**2 + hwhm**2)


def fit_lorentzian(t, y):
    """Fit a peak-or-dip Lorentzian to y(t).

    Returns a dict with keys:
        success : bool                       did the fit converge?
        params  : {t0, fwhm, amp, offset}    best-fit values (empty if failed)
        perr    : {t0, fwhm, amp, offset}    1-sigma std errors from the covariance
        r2      : float                      coefficient of determination
        rms     : float                      RMS of the residuals (volts)
        t_fit   : np.ndarray                 dense t for plotting the model
        y_fit   : np.ndarray                 model evaluated on t_fit
        message : str                        human-readable status / failure reason
    """
    fail = lambda msg: {"success": False, "params": {}, "perr": {},
                        "r2": float("nan"), "rms": float("nan"),
                        "t_fit": np.array([]), "y_fit": np.array([]),
                        "message": msg}

    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    if t.size < 4 or y.size != t.size:
        return fail("Not enough samples to fit.")
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(y))):
        return fail("Data contains non-finite values.")

    span = float(t[-1] - t[0])
    if span <= 0:
        return fail("Time axis is not increasing.")

    # --- initial guesses ---------------------------------------------------
    offset0 = float(np.median(y))
    up, down = float(np.max(y) - offset0), float(offset0 - np.min(y))
    if up >= down:                       # peak
        amp0 = up
        t0_0 = float(t[int(np.argmax(y))])
    else:                                # dip
        amp0 = -down
        t0_0 = float(t[int(np.argmin(y))])
    if amp0 == 0:
        return fail("Signal is flat; nothing to fit.")
    fwhm0 = span / 10.0
    p0 = [t0_0, fwhm0, amp0, offset0]

    # bounds: t0 within the window, fwhm positive and not wider than the span,
    # amp free in sign, offset free.
    dt = span / max(1, t.size - 1)
    lower = [t[0], dt, -np.inf, -np.inf]
    upper = [t[-1], span, np.inf, np.inf]

    try:
        popt, pcov = curve_fit(lorentzian, t, y, p0=p0,
                               bounds=(lower, upper), maxfev=10000)
    except (RuntimeError, ValueError) as exc:
        return fail(f"curve_fit did not converge ({exc}).")

    perr_arr = np.sqrt(np.diag(pcov)) if np.all(np.isfinite(pcov)) else np.full(4, np.nan)

    y_model = lorentzian(t, *popt)
    resid = y - y_model
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - np.mean(y))**2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    rms = float(np.sqrt(np.mean(resid**2)))

    keys = ["t0", "fwhm", "amp", "offset"]
    t_fit = np.linspace(t[0], t[-1], min(2000, max(t.size, 2)))
    return {
        "success": True,
        "params": dict(zip(keys, (float(p) for p in popt))),
        "perr": dict(zip(keys, (float(e) for e in perr_arr))),
        "r2": r2,
        "rms": rms,
        "t_fit": t_fit,
        "y_fit": lorentzian(t_fit, *popt),
        "message": "Fit converged.",
    }


_WINDOWS = {
    "rectangular": np.ones,
    "hann": np.hanning,
    "hamming": np.hamming,
    "blackman": np.blackman,
}


def compute_spectrum(t, y, window="hann", scaling="amplitude"):
    """One-sided amplitude/PSD spectrum of a uniformly-sampled real signal y(t).

    window  : "rectangular" | "hann" | "hamming" | "blackman" — the taper applied
              before the FFT to control spectral leakage.
    scaling : "amplitude" -> peak amplitude per frequency bin, units V (a sinusoid
                             of amplitude A reads A at its line, window-independent);
              "asd"        -> amplitude spectral density, units V/√Hz (flat for white
                             noise, the natural quantity for noise-floor work).

    Returns a dict (mirrors fit_lorentzian's style):
        success : bool
        f       : np.ndarray   one-sided frequency axis (Hz)
        mag     : np.ndarray   spectrum in the requested units
        units   : str          "V" or "V/√Hz"
        fs      : float        sampling rate (Hz)
        df      : float        bin spacing fs/N (Hz)
        enbw    : float        equivalent noise bandwidth of the window (Hz)
        nyquist : float        fs/2 (Hz)
        message : str
    """
    fail = lambda msg: {"success": False, "f": np.array([]), "mag": np.array([]),
                        "units": "", "fs": float("nan"), "df": float("nan"),
                        "enbw": float("nan"), "nyquist": float("nan"),
                        "message": msg}

    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 4 or t.size != n:
        return fail("Not enough samples for an FFT.")
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(y))):
        return fail("Data contains non-finite values.")

    span = float(t[-1] - t[0])
    if span <= 0:
        return fail("Time axis is not increasing.")
    fs = (n - 1) / span

    win_fn = _WINDOWS.get(window, np.hanning)
    w = win_fn(n)
    s1 = float(w.sum())
    s2 = float((w * w).sum())
    if s1 == 0:
        return fail("Degenerate window.")

    Y = np.fft.rfft(y * w)
    f = np.fft.rfftfreq(n, d=1.0 / fs)

    # one-sided correction: double every bin except DC and (for even n) Nyquist.
    two = np.full(Y.size, 2.0)
    two[0] = 1.0
    if n % 2 == 0:
        two[-1] = 1.0

    if scaling == "asd":
        psd = two * np.abs(Y) ** 2 / (fs * s2)   # V²/Hz, one-sided
        mag = np.sqrt(psd)
        units = "V/√Hz"
    else:
        mag = two * np.abs(Y) / s1               # peak amplitude per bin, V
        units = "V"

    return {
        "success": True,
        "f": f,
        "mag": mag,
        "units": units,
        "fs": fs,
        "df": fs / n,
        "enbw": fs * s2 / (s1 * s1),
        "nyquist": fs / 2.0,
        "message": "OK.",
    }


# ---------------------------------------------------------------------------
# VRS–cavity alignment: double/single Lorentzian asymmetry
#
# A cavity-length step produces one triggered shot with two TTL-gated windows on
# a signal channel: window 1 is a *double* Lorentzian (the VRS doublet), window 2
# a *single* Lorentzian (bare cavity). Both windows are identical frequency
# ramps, so a peak's position *within its own window* maps linearly to frequency.
# The "asymmetry" is the time gap between the doublet center (midpoint of the two
# peaks) and the single peak center, converted to kHz via the scan rate; it is
# zero when the atomic line sits on the cavity resonance.
# ---------------------------------------------------------------------------


def single_lorentzian(t, A, x0, gamma, offset):
    """One Lorentzian peak. `gamma` is FWHM; `A` is the peak height above `offset`."""
    return A * (gamma / 2.0) ** 2 / ((t - x0) ** 2 + (gamma / 2.0) ** 2) + offset


def double_lorentzian(t, A1, x1, g1, A2, x2, g2, offset):
    """Sum of two Lorentzian peaks sharing one baseline `offset` (FWHM = g1, g2)."""
    l1 = A1 * (g1 / 2.0) ** 2 / ((t - x1) ** 2 + (g1 / 2.0) ** 2)
    l2 = A2 * (g2 / 2.0) ** 2 / ((t - x2) ** 2 + (g2 / 2.0) ** 2)
    return l1 + l2 + offset


def segment_ttl(t, ttl, threshold, min_width=0.0):
    """Find clean TTL-high windows in ttl(t).

    Pairs each rising edge with the next falling edge. Pulses that touch a data
    edge (TTL already high at t[0], or still high at t[-1]) are dropped, as are
    pulses narrower than `min_width` (seconds). Returns a list of
    ``(start_idx, stop_idx)`` half-open index slices, so ``t[start:stop]`` /
    ``sig[start:stop]`` are the high-region samples.
    """
    t = np.asarray(t, dtype=float)
    ttl = np.asarray(ttl, dtype=float)
    if ttl.size < 2:
        return []

    high = ttl > threshold
    d = np.diff(high.astype(np.int8))
    rises = np.where(d == 1)[0] + 1     # first sample that is high
    falls = np.where(d == -1)[0] + 1    # first sample that is low again

    windows = []
    fi = 0
    for r in rises:
        while fi < falls.size and falls[fi] <= r:
            fi += 1                     # skip falls with no matching rise (leading edge)
        if fi >= falls.size:
            break                       # rise with no fall: still high at t[-1], drop
        f = int(falls[fi])
        fi += 1
        if t[f - 1] - t[r] >= min_width:
            windows.append((int(r), f))
    return windows


def _r2(y, y_model):
    """Coefficient of determination, or nan if the data has no variance."""
    resid = y - y_model
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot <= 0:
        return float("nan")
    return 1.0 - float(np.sum(resid ** 2)) / ss_tot


def fit_window_asymmetry(t, sig, ttl, scale_khz_per_s, threshold=1.0,
                         min_width=0.0, gof_min=0.5, factor=1.0):
    """Fit the double/single Lorentzians in one two-TTL-window shot and return the
    doublet-vs-single center asymmetry, in kHz.

    t, sig, ttl     : 1-D arrays, time (s) and the two channels (V).
    scale_khz_per_s : (scan_range_Hz / scan_time_s) * 1e-3, the time->kHz scaling.
    threshold       : TTL high threshold (V).
    min_width       : drop TTL pulses narrower than this (s).
    gof_min         : reject the shot if min(R²_double, R²_single) falls below this.
    factor          : multiplier on the asymmetry (1.0 = center_double - center_single).

    Never raises. Returns a dict (mirrors fit_lorentzian's style):
        success         : bool
        message         : str    status / failure reason
        asymm_khz       : float
        asymm_err_khz   : float  1-sigma, propagated from the fit covariances
        gof             : float  min(R²_double, R²_single)
        center_double   : float  midpoint of the two doublet peaks (s, within window)
        center_single   : float  single peak center (s, within window)
        popt_double     : np.ndarray (7,) or empty
        popt_single     : np.ndarray (4,) or empty
        t1, y1, y1_fit  : np.ndarray  doublet window data + model (absolute time)
        t2, y2, y2_fit  : np.ndarray  single window data + model (absolute time)
    """
    empty = np.array([])
    fail = lambda msg: {"success": False, "message": msg,
                        "asymm_khz": float("nan"), "asymm_err_khz": float("nan"),
                        "gof": float("nan"), "center_double": float("nan"),
                        "center_single": float("nan"),
                        "popt_double": empty, "popt_single": empty,
                        "t1": empty, "y1": empty, "y1_fit": empty,
                        "t2": empty, "y2": empty, "y2_fit": empty}

    t = np.asarray(t, dtype=float)
    sig = np.asarray(sig, dtype=float)
    ttl = np.asarray(ttl, dtype=float)
    if t.size < 8 or sig.size != t.size or ttl.size != t.size:
        return fail("Not enough samples.")
    if not (np.all(np.isfinite(t)) and np.all(np.isfinite(sig))
            and np.all(np.isfinite(ttl))):
        return fail("Data contains non-finite values.")

    windows = segment_ttl(t, ttl, threshold, min_width)
    if len(windows) != 2:
        return fail(f"Expected 2 TTL windows, found {len(windows)}.")

    (s1, e1), (s2, e2) = windows
    t1, y1 = t[s1:e1], sig[s1:e1]   # window 1 -> double
    t2, y2 = t[s2:e2], sig[s2:e2]   # window 2 -> single
    if t1.size < 6 or t2.size < 4:
        return fail("TTL window too short to fit.")

    # Re-zero each window to its own start: the peak position *within* the ramp is
    # what maps to frequency, so centers must be measured from each window's edge.
    t1r, t2r = t1 - t1[0], t2 - t2[0]
    span1, span2 = float(t1r[-1]), float(t2r[-1])
    dt1, dt2 = span1 / max(1, t1r.size - 1), span2 / max(1, t2r.size - 1)

    ptp1, ptp2 = float(np.ptp(y1)), float(np.ptp(y2))
    if ptp1 <= 0 or ptp2 <= 0:
        return fail("Signal is flat in a TTL window.")

    # --- doublet seed: two most-prominent peaks, else split-window argmax -------
    off1 = float(np.min(y1))
    g1_0 = span1 / 20.0 or dt1
    pk1, props1 = find_peaks(y1, prominence=0.1 * ptp1,
                             distance=max(1, t1r.size // 20))
    if pk1.size >= 2:
        top2 = pk1[np.argsort(props1["prominences"])[::-1][:2]]
        ia, ib = int(np.min(top2)), int(np.max(top2))   # left, right
    else:
        half = t1r.size // 2
        ia = int(np.argmax(y1[:half]))
        ib = half + int(np.argmax(y1[half:]))
    p0_d = [max(y1[ia] - off1, dt1), t1r[ia], g1_0,
            max(y1[ib] - off1, dt1), t1r[ib], g1_0, off1]
    lo_d = [0.0, 0.0, dt1, 0.0, 0.0, dt1, -np.inf]
    hi_d = [np.inf, span1, span1, np.inf, span1, span1, np.inf]

    # --- single seed: most-prominent peak, else global argmax ------------------
    off2 = float(np.min(y2))
    g2_0 = span2 / 20.0 or dt2
    pk2, props2 = find_peaks(y2, prominence=0.1 * ptp2,
                             distance=max(1, t2r.size // 20))
    ic = (int(pk2[np.argmax(props2["prominences"])]) if pk2.size
          else int(np.argmax(y2)))
    p0_s = [max(y2[ic] - off2, dt2), t2r[ic], g2_0, off2]
    lo_s = [0.0, 0.0, dt2, -np.inf]
    hi_s = [np.inf, span2, span2, np.inf]

    try:
        popt_d, pcov_d = curve_fit(double_lorentzian, t1r, y1, p0=p0_d,
                                   bounds=(lo_d, hi_d), maxfev=20000)
        popt_s, pcov_s = curve_fit(single_lorentzian, t2r, y2, p0=p0_s,
                                   bounds=(lo_s, hi_s), maxfev=20000)
    except (RuntimeError, ValueError) as exc:
        return fail(f"curve_fit did not converge ({exc}).")

    r2d = _r2(y1, double_lorentzian(t1r, *popt_d))
    r2s = _r2(y2, single_lorentzian(t2r, *popt_s))
    gof = float(np.nanmin([r2d, r2s]))
    if not np.isfinite(gof) or gof < gof_min:
        return fail(f"Poor fit (R² = {gof:.3f} < {gof_min:.2f}).")

    x1, x2 = float(popt_d[1]), float(popt_d[4])
    center_double = 0.5 * (x1 + x2)
    center_single = float(popt_s[1])
    asymm_s = center_double - center_single
    asymm_khz = factor * scale_khz_per_s * asymm_s

    err_d = np.sqrt(np.diag(pcov_d)) if np.all(np.isfinite(pcov_d)) else np.full(7, np.nan)
    err_s = np.sqrt(np.diag(pcov_s)) if np.all(np.isfinite(pcov_s)) else np.full(4, np.nan)
    center_double_err = 0.5 * np.hypot(err_d[1], err_d[4])
    asymm_s_err = float(np.hypot(center_double_err, err_s[1]))
    asymm_err_khz = abs(factor * scale_khz_per_s) * asymm_s_err

    return {
        "success": True,
        "message": "Fit converged.",
        "asymm_khz": float(asymm_khz),
        "asymm_err_khz": float(asymm_err_khz),
        "gof": gof,
        "center_double": center_double,
        "center_single": center_single,
        "popt_double": popt_d,
        "popt_single": popt_s,
        "t1": t1, "y1": y1, "y1_fit": double_lorentzian(t1r, *popt_d),
        "t2": t2, "y2": y2, "y2_fit": single_lorentzian(t2r, *popt_s),
    }

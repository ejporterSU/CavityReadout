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

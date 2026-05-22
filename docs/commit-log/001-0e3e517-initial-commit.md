# 001 — Initial commit: Cleverscope oscilloscope control driver

- **Commit:** `0e3e5179b207efcd12d8f276836abf79b4a90b7b`
- **Date:** 2026-05-21

## What
Created the git repo and published it to GitHub (ejporterSU/CavityReadout) with
the existing Cleverscope control code. Added a `.gitignore` (Python, Jupyter
checkpoints, venvs, IDE/OS files, and local Claude settings). No README by request.

Files committed (12, +4190 lines):
- `Cscope control driver/cscope_class.py` — the `CScope` class written to control
  the scope (connect, time axis, trigger, per-channel range/coupling, acquisition).
- `Cscope control driver/CleverscopeTesting.ipynb` — the working analysis/testing
  notebook (cavity scans, heterodyne demod, noise floor, sweeps).
- Vendor files from Cleverscope: `CleverscopeInterface.py`, `CleverscopeClasses.py`,
  `T_AcquireSpec.py`, `T_ChannelSpec.py`, `T_InterfaceSpec.py`, `T_ReplaySpec.py`,
  `T_T0dt.py`, plus `CleverscopeExample.py` and `CleverscopeExample - 4 Scopes.py`.

## Why
Get the existing instrument-control code under version control before building a
new readout interface on top of it.

## Notes for future work
- The vendor `CleverscopeInterface` loads the DLL via a **relative** path
  (`Cscope control driver\Cscope control driver 64.dll`), and that DLL is **not**
  in the repo. Code won't run against hardware without it.
- Vendor modules use flat imports (`import CleverscopeInterface`), so the
  `Cscope control driver` folder must be on `sys.path`.

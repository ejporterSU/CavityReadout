# 006 — Hardware bring-up fixes (real scope, NumPy 2.0)

- **Commit:** (this commit — see `git log`)
- **Date:** 2026-05-22

## Context
First run on a machine with the actual Cleverscope (serial `EQ10014`) attached and
the vendor binaries (`Cscope control driver 64.dll` + `.h/.lib/.ini/.aliases`) and
flat vendor Python modules placed in `Cscope control driver/`. Up to now everything
had only run under `--simulate` (the `MockScope` path), so three real-hardware-only
defects had never been exercised. Each surfaced in turn while bringing the scope up
from the testing notebook and the GUI; this commit fixes all three.

## What
- `Cscope control driver/T_InterfaceSpec.py` — `convertSerialNumberToUINT32` used
  `np.fromstring(s, dtype=np.uint8)` (binary mode) to turn serial-number chars into
  bytes. **NumPy 2.0 removed the binary mode of `fromstring`**, so connect threw
  *"The binary mode of fromstring is removed, use frombuffer instead"*. Replaced with
  `np.frombuffer(s[::-1].encode('latin-1'), dtype=np.uint8)`. The serial chars are
  ASCII, so latin-1 reproduces the exact bytes the old call produced.
- `Cscope control driver/CleverscopeInterface.py` — the DLL was loaded by the
  relative path `"Cscope control driver\\Cscope control driver 64.dll"`, which only
  resolves when the working directory is the repo root. Running the notebook (whose
  CWD is its own folder) produced a doubled, nonexistent path
  (`...\Cscope control driver\Cscope control driver\...dll`). Now loaded from an
  absolute path derived from the module's own location
  (`os.path.dirname(os.path.abspath(__file__))`), so it works regardless of CWD —
  notebook, `run_scope.py`, or anywhere.
- `Cscope control driver/cscope_class.py`:
  - `disconnect()` sent `T_Command_Close` **and** `T_Command_Finish`. `Finish` tears
    down the entire LabVIEW driver runtime and **blocks indefinitely** (forcing a
    kernel restart), and leaves the runtime closed so you can't reconnect in the same
    session. The vendor's own `CleverscopeExample - 4 Scopes.py` shuts down with
    `Close` alone — matched that. `disconnect()` now also resets `self.scope = None`
    / `self.is_connected = False` (it previously left them set).
  - Added `IsConnected()` method. `ScopeController.connected` calls
    `self._scope.IsConnected()`; `MockScope` had it but the real `CScope` only had an
    `is_connected` *attribute*, so the GUI threw `AttributeError` the moment a real
    connection succeeded.
  - `__init__` now sets `self.is_connected = False` (it was read in `__del__` but
    never initialized, so GC of a never-connected `CScope` would raise).

## Why
Hardware-only code paths that `--simulate` never touches: the `MockScope` supplies
its own `connect`/`disconnect`/`IsConnected` and never builds a `T_InterfaceSpec` or
loads the DLL, so the serial-conversion, DLL-path, disconnect-hang, and missing-
`IsConnected` bugs were all invisible until a real scope was on the bench with a
NumPy-2.0 environment.

## Verification
- Serial conversion: `T_InterfaceSpec("EQ10014", ...)` builds under NumPy 2.x;
  `CAUSerNumHi=4542769`, `CAUSerNumLo=808464692`.
- Connect from repo root **and** from inside `Cscope control driver/` (the doubled-
  path case): both print `Success: Connected to EQ10014`.
- Disconnect: `Close`-only returns immediately; no hang, and reconnect works in the
  same process without a restart.
- Trigger channel: set A/B/C/D in turn and read back via `GetTriggerSettings` — the
  driver reports the matching source each time (the enum values are non-sequential:
  A=0, B=1, C=5, D=6). Triggering on a channel still requires the trigger **level**
  to lie within that channel's input range, or the capture won't fire.

## Notes for future work
- The vendor binaries are not in git (ignored). Hardware runs need them present in
  `Cscope control driver/`; a fresh clone on a new machine must have them copied in.
- `T_Command_Finish` (full runtime teardown) is intentionally never sent now. If a
  true process-exit "close the driver library" is ever needed, do it once at
  interpreter shutdown, not per-disconnect.
- These vendor modules are authored upstream (mattkatz / RHC); the edits are minimal,
  targeted compatibility fixes. Re-check them if the vendor driver is ever updated.

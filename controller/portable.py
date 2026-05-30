"""Cross-platform helpers used by the runner and the controller.

Three things differ enough between macOS / Linux / Windows to deserve their
own module:

  * "give the child its own kill-able group" — `start_new_session=True` on
    POSIX, `creationflags=CREATE_NEW_PROCESS_GROUP` on Windows.
  * "kill the whole tree" — `os.killpg(..., SIGKILL)` on POSIX, `taskkill
    /F /T /PID ...` on Windows.
  * "what executable extension do compiled binaries end with" — empty on
    POSIX, `.exe` on Windows.

Everything else in the project sticks to the standard library and is portable
without help.
"""

import os
import re
import signal
import subprocess
import sys


def slug(name: str) -> str:
    """Stable, filesystem-safe, URL-safe identifier for a language name.

    Critically: `++` becomes `pp` and `#` becomes `sharp` *before* the
    non-alphanumeric collapse, so `C` and `C++` end up with different slugs
    (`c` vs `cpp`) instead of colliding into one work directory.
    """
    s = name.lower()
    s = s.replace("++", "pp").replace("#", "sharp")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "lang"


def current_platform() -> str:
    """Return one of: 'windows', 'darwin', 'linux'.

    (The BSDs and other Unixes are bucketed as 'linux' for our purposes —
    they share the POSIX subprocess model, which is all we use this for.)
    """
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def exe_suffix() -> str:
    return ".exe" if os.name == "nt" else ""


def popen_isolation_kwargs() -> dict:
    """Kwargs that put the child in its own process group / job so we can
    kill the whole tree on timeout."""
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP lets taskkill /T reach descendants reliably.
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(proc) -> None:
    """Kill `proc` and any descendants. Best-effort; never raises.

    On POSIX we kill the whole process group; on Windows we use
    `taskkill /F /T` which walks the child tree."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        pass

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    # Final safety net: directly kill the immediate child.
    try:
        proc.kill()
    except Exception:
        pass


def install_shutdown_signals(handler=signal.default_int_handler) -> None:
    """Route SIGTERM (and SIGHUP on POSIX) through the same KeyboardInterrupt
    path Ctrl+C uses, so cleanup runs no matter how we're asked to stop.

    Safe to call on Windows — SIGHUP simply doesn't exist there."""
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError, AttributeError):
            pass

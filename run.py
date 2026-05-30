#!/usr/bin/env python3
"""Wall of Hello World — controller / entry point.

Pipeline:  detect & run every language once  ->  collect results  ->
render one full-screen page  ->  serve it on localhost  ->  open it ->
wait for the centre button (/exit)  ->  kill the browser, delete temp files,
exit. Nothing is left running.

Usage:
    python3 run.py                 run the wall and open it full-screen
    python3 run.py --no-open       serve but don't open a browser (prints URL)
    python3 run.py --dry-run       just run the languages and print a table
    python3 run.py --list          list languages + availability, run nothing
    python3 run.py --timeout 40    override the default per-step timeout (s)
"""

import argparse
import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser

# Allow running as `python3 run.py` from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from controller import page, runner, server  # noqa: E402
from controller.languages import get_languages  # noqa: E402
from controller.portable import (current_platform, install_shutdown_signals,
                                 kill_tree, popen_isolation_kwargs)  # noqa: E402

C_GREEN, C_YELLOW, C_GREY, C_DIM, C_RST = (
    "\033[32m", "\033[33m", "\033[90m", "\033[2m", "\033[0m")
_SYMBOL = {
    runner.STATUS_SUCCESS: (C_GREEN, "ok "),
    runner.STATUS_FAILED: (C_YELLOW, "err"),
    runner.STATUS_UNAVAILABLE: (C_GREY, "n/a"),
}

def _find_chrome():
    """Return a path to a Chromium-family browser if one is installed, else
    None. Checked per-OS using the canonical install locations."""
    plat = current_platform()
    if plat == "darwin":
        for path in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ):
            if os.path.exists(path):
                return path
        return None
    if plat == "windows":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(pfx, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe") if local else None,
            os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(pfx, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(pf, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(pfx, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None
    # linux
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "microsoft-edge", "brave-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _print_summary(results):
    print("\n  " + C_DIM + "language".ljust(20) + "status   time   output" + C_RST)
    print("  " + C_DIM + "-" * 58 + C_RST)
    for r in sorted(results, key=lambda x: x.name.lower()):
        color, tag = _SYMBOL.get(r.status, (C_RST, "?"))
        detail = r.output if r.status == runner.STATUS_SUCCESS else (
            r.error or "runtime not installed")
        detail = detail.splitlines()[0] if detail else ""
        if len(detail) > 28:
            detail = detail[:27] + "…"
        t = f"{r.elapsed_ms:>4}ms" if r.elapsed_ms else "   -  "
        print(f"  {r.name.ljust(20)}{color}{tag}{C_RST}   {t}  {C_DIM}{detail}{C_RST}")
    live = sum(1 for r in results if r.status == runner.STATUS_SUCCESS)
    failed = sum(1 for r in results if r.status == runner.STATUS_FAILED)
    na = sum(1 for r in results if r.status == runner.STATUS_UNAVAILABLE)
    print("  " + C_DIM + "-" * 58 + C_RST)
    print(f"  {C_GREEN}{live} live{C_RST} · {C_YELLOW}{failed} failed{C_RST} · "
          f"{C_GREY}{na} unavailable{C_RST}  (of {len(results)})\n")


def _launch_browser(url, tmp):
    """Open the wall full-screen. Returns a Popen we can kill, or None."""
    chrome = _find_chrome()
    if chrome:
        profile = os.path.join(tmp, "browser-profile")
        args = [
            chrome, f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check",
            "--new-window", "--start-fullscreen", f"--app={url}",
        ]
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **popen_isolation_kwargs(),
            )
            print(f"  opened full-screen in {os.path.basename(chrome)}")
            return proc
        except OSError:
            pass
    webbrowser.open(url)
    hint = {
        "darwin":  "press Cmd+Ctrl+F for full screen",
        "linux":   "press F11 for full screen",
        "windows": "press F11 for full screen",
    }[current_platform()]
    print(f"  opened in your default browser ({hint})")
    return None


def main():
    ap = argparse.ArgumentParser(description="Wall of Hello World")
    ap.add_argument("--no-open", action="store_true",
                    help="serve but do not open a browser")
    ap.add_argument("--dry-run", action="store_true",
                    help="run languages, print a table, then exit")
    ap.add_argument("--list", action="store_true",
                    help="list languages and availability, run nothing")
    ap.add_argument("--timeout", type=float, default=runner.DEFAULT_TIMEOUT,
                    help="per-step timeout in seconds")
    args = ap.parse_args()

    # Flush per line even when output is piped, so the URL shows up promptly.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    langs = get_languages()

    if args.list:
        plat = current_platform()
        print(f"\n  {len(langs)} languages registered (platform: {plat}):\n")
        for lang in langs:
            if lang.kind == "browser":
                state = f"{C_GREEN}browser{C_RST}"
            elif lang.platforms and plat not in lang.platforms:
                need = " or ".join(lang.platforms)
                state = f"{C_GREY}n/a (requires {need}){C_RST}"
            else:
                missing = [e for e in lang.checks if shutil.which(e) is None]
                state = (f"{C_GREY}n/a (missing: {', '.join(missing)}){C_RST}"
                         if missing else f"{C_GREEN}available{C_RST}")
            print(f"  {lang.name.ljust(20)} {lang.category.ljust(9)} {state}")
        print()
        return 0

    tmp = tempfile.mkdtemp(prefix="hww-")
    browser = None
    cleaned = {"done": False}

    def cleanup():
        if cleaned["done"]:
            return
        cleaned["done"] = True
        kill_tree(browser)
        shutil.rmtree(tmp, ignore_errors=True)

    # Always clean up, however we exit. Route SIGTERM (and SIGHUP on POSIX)
    # through the same KeyboardInterrupt path we already handle. Safe to call
    # on Windows — SIGHUP simply doesn't exist there and is skipped.
    atexit.register(cleanup)
    install_shutdown_signals()

    try:
        print(f"\n  Running {len(langs)} languages "
              f"(timeout {args.timeout:g}s each, up to {runner.MAX_PARALLEL} at once)…")

        def progress(done, total, r):
            color, tag = _SYMBOL.get(r.status, (C_RST, "?"))
            sys.stdout.write(
                f"\r  [{done:>2}/{total}] {color}{tag}{C_RST} {r.name.ljust(22)}")
            sys.stdout.flush()

        results = runner.collect(langs, tmp, args.timeout, progress=progress)
        sys.stdout.write("\r" + " " * 50 + "\r")
        _print_summary(results)

        if args.dry_run:
            cleanup()
            return 0

        html = page.render_page(results)
        srv = server.WallServer(html, on_exit=lambda: _kill_group(browser))
        url = srv.url
        print(f"  Serving the wall at {url}")

        if not args.no_open:
            browser = _launch_browser(url, tmp)
        else:
            print("  (--no-open) open the URL yourself; GET /exit to stop.")

        print(f"  {C_DIM}Click END PROJECT in the page (or Ctrl+C here) to shut down.{C_RST}\n")
        try:
            srv.serve_forever()           # returns when /exit calls shutdown()
        except KeyboardInterrupt:
            print("\n  Ctrl+C — shutting down…")
            srv._on_exit = None           # kill browser via cleanup() instead
        finally:
            srv.server_close()
    finally:
        cleanup()

    print("  Done. Nothing left running.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

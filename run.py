#!/usr/bin/env python3
"""Wall of Hello World — controller / entry point.

Streaming flow:
  start server immediately  →  open browser to placeholder grid  →
  run every language in parallel on a background thread, publishing each
  result to the page over Server-Sent Events as it completes  →
  wait for END PROJECT (/exit) or Ctrl+C  →  kill the browser, delete the
  temp dir, exit. Nothing is left running.

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
import threading
import webbrowser

# Allow running as `python3 run.py` from anywhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from controller import page, runner, server  # noqa: E402
from controller.languages import get_languages  # noqa: E402
from controller.portable import (current_platform, install_shutdown_signals,
                                 kill_tree, popen_isolation_kwargs,
                                 slug)  # noqa: E402

C_GREEN, C_YELLOW, C_GREY, C_DIM, C_RST = (
    "\033[32m", "\033[33m", "\033[90m", "\033[2m", "\033[0m")
_SYMBOL = {
    runner.STATUS_SUCCESS: (C_GREEN, "ok "),
    runner.STATUS_FAILED: (C_YELLOW, "err"),
    runner.STATUS_UNAVAILABLE: (C_GREY, "n/a"),
}


def _find_chrome():
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
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "microsoft-edge", "brave-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _launch_browser(url, tmp):
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


def _print_dry_summary(results):
    print("\n  " + C_DIM + "language".ljust(20) + "status   time   output" + C_RST)
    print("  " + C_DIM + "-" * 78 + C_RST)
    for r in sorted(results, key=lambda x: x.name.lower()):
        color, tag = _SYMBOL.get(r.status, (C_RST, "?"))
        detail = r.output if r.status == runner.STATUS_SUCCESS else (
            r.error or "runtime not installed")
        detail = detail.splitlines()[0] if detail else ""
        if len(detail) > 48:
            detail = detail[:47] + "…"
        t = f"{r.elapsed_ms:>5}ms" if r.elapsed_ms else "    -  "
        print(f"  {r.name.ljust(20)}{color}{tag}{C_RST}  {t}  {C_DIM}{detail}{C_RST}")
    live = sum(1 for r in results if r.status == runner.STATUS_SUCCESS)
    failed = sum(1 for r in results if r.status == runner.STATUS_FAILED)
    na = sum(1 for r in results if r.status == runner.STATUS_UNAVAILABLE)
    print("  " + C_DIM + "-" * 78 + C_RST)
    print(f"  {C_GREEN}{live} live{C_RST} · {C_YELLOW}{failed} failed{C_RST} · "
          f"{C_GREY}{na} unavailable{C_RST}  (of {len(results)})\n")


def _result_to_payload(r):
    return {
        "slug": slug(r.name),
        "name": r.name,
        "status": r.status,
        "output": r.output,
        "command": r.command,
        "error": r.error,
        "elapsed_ms": r.elapsed_ms,
        "category": r.category,
        "note": r.note,
        "matched": r.matched,
        "creator": r.creator,
        "since": r.since,
        "missing": list(r.missing or []),
    }


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

    langs_all = get_languages()
    plat = current_platform()

    if args.list:
        print(f"\n  {len(langs_all)} languages registered (platform: {plat}):\n")
        for lang in langs_all:
            if lang.kind == "browser":
                state = f"{C_GREEN}browser{C_RST}"
            elif lang.platforms and plat not in lang.platforms:
                state = f"{C_GREY}n/a (requires {' or '.join(lang.platforms)}){C_RST}"
            else:
                missing = [e for e in lang.checks if shutil.which(e) is None]
                state = (f"{C_GREY}n/a (missing: {', '.join(missing)}){C_RST}"
                         if missing else f"{C_GREEN}available{C_RST}")
            print(f"  {lang.name.ljust(20)} {lang.category.ljust(9)} {state}")
        print()
        return 0

    # Hide tiles that can never run on this OS (they're kept in the registry
    # so the same code base can be used cross-platform — they just don't
    # appear on the wall here).
    langs = [l for l in langs_all if not l.platforms or plat in l.platforms]
    hidden = len(langs_all) - len(langs)

    tmp = tempfile.mkdtemp(prefix="hww-")
    browser = None
    cleaned = {"done": False}

    def cleanup():
        if cleaned["done"]:
            return
        cleaned["done"] = True
        kill_tree(browser)
        shutil.rmtree(tmp, ignore_errors=True)

    atexit.register(cleanup)
    install_shutdown_signals()

    try:
        # --dry-run: keep the old pre-render-then-print-table flow.
        if args.dry_run:
            print(f"\n  Running {len(langs)} languages "
                  f"(timeout {args.timeout:g}s each, up to {runner.MAX_PARALLEL} at once)…")

            def progress(done, total, r):
                color, tag = _SYMBOL.get(r.status, (C_RST, "?"))
                sys.stdout.write(
                    f"\r  [{done:>2}/{total}] {color}{tag}{C_RST} {r.name.ljust(22)}")
                sys.stdout.flush()

            results = runner.collect(langs, tmp, args.timeout, progress=progress)
            sys.stdout.write("\r" + " " * 60 + "\r")
            _print_dry_summary(results)
            return 0

        # Streaming mode: serve the placeholder grid immediately, kick the
        # runner off on a background thread, push each result to the page.
        broker = server.SSEBroker()
        html_text = page.render_initial(langs)
        srv = server.WallServer(html_text, broker=broker,
                                on_exit=lambda: kill_tree(browser))
        url = srv.url

        msg = f"\n  Serving the wall at {url}"
        if hidden:
            msg += f"  ({hidden} tile{'s' if hidden != 1 else ''} hidden — restricted to other OSes)"
        print(msg)
        print(f"  Streaming results for {len(langs)} languages "
              f"(timeout {args.timeout:g}s each, up to {runner.MAX_PARALLEL} at once)…\n")

        if not args.no_open:
            browser = _launch_browser(url, tmp)
        else:
            print("  (--no-open) open the URL yourself; GET /exit to stop.")

        # Background runner thread.
        live_counts = {"ok": 0, "fail": 0, "na": 0}

        def progress(done, total, r):
            broker.publish("result", _result_to_payload(r))
            color, tag = _SYMBOL.get(r.status, (C_RST, "?"))
            sys.stdout.write(
                f"\r  [{done:>2}/{total}] {color}{tag}{C_RST} {r.name.ljust(22)}")
            sys.stdout.flush()
            if r.status == runner.STATUS_SUCCESS:
                live_counts["ok"] += 1
            elif r.status == runner.STATUS_FAILED:
                live_counts["fail"] += 1
            else:
                live_counts["na"] += 1

        def run_languages():
            try:
                runner.collect(langs, tmp, args.timeout, progress=progress)
            finally:
                broker.signal_done()
                sys.stdout.write("\r" + " " * 60 + "\r")
                print(f"  All done: {C_GREEN}{live_counts['ok']} live{C_RST} · "
                      f"{C_YELLOW}{live_counts['fail']} failed{C_RST} · "
                      f"{C_GREY}{live_counts['na']} n/a{C_RST}  "
                      f"(of {len(langs)})")
                print(f"  {C_DIM}Click END PROJECT in the page (or Ctrl+C) to shut down.{C_RST}\n")

        threading.Thread(target=run_languages, daemon=True).start()

        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n  Ctrl+C — shutting down…")
            srv._on_exit = None
        finally:
            srv.server_close()
    finally:
        cleanup()

    print("  Done. Nothing left running.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

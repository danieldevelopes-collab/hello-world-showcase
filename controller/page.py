"""Renders the captured results into one dramatic full-screen HTML page.

The page is fully self-contained (no external assets, no network) and is held
in memory by the server. The centre button calls /exit on the controller.
"""

import html
from typing import Dict, List

from .runner import (Result, STATUS_FAILED, STATUS_SUCCESS,
                     STATUS_UNAVAILABLE)

_ORDER = {STATUS_SUCCESS: 0, STATUS_FAILED: 1, STATUS_UNAVAILABLE: 2}


def _tile(r: Result) -> str:
    name = html.escape(r.name)
    note = html.escape(r.note) if r.note else ""
    note_html = f'<span class="note">{note}</span>' if note else ""

    credit_parts = []
    if r.creator:
        credit_parts.append(f"by {html.escape(r.creator)}")
    if r.since:
        credit_parts.append(html.escape(r.since))
    credit_html = (f'<span class="credit">{" · ".join(credit_parts)}</span>'
                   if credit_parts else "")

    if r.status == STATUS_SUCCESS:
        status_cls = "ok"
        badge = "LIVE" if r.real else "SIM"
        if r.name == "HTML / JavaScript":
            body = '<div class="out" id="browser-js">running…</div>'
        else:
            body = f'<div class="out">{html.escape(r.output) or "Hello World"}</div>'
        meta = f'<code>{html.escape(r.command)}</code><span>{r.elapsed_ms} ms</span>'
    elif r.status == STATUS_UNAVAILABLE:
        status_cls = "na"
        badge = "N/A"
        miss = ", ".join(r.missing)
        body = '<div class="out muted">runtime not installed</div>'
        meta = f'<code>missing: {html.escape(miss)}</code>'
    else:  # failed
        status_cls = "err"
        badge = "FAIL"
        detail = html.escape(r.output)[:300]
        body = (f'<div class="out err-text">{html.escape(r.error)}</div>'
                f'<div class="errlog">{detail}</div>')
        meta = f'<code>{html.escape(r.command)}</code><span>{r.elapsed_ms} ms</span>'

    return (
        f'<div class="tile {status_cls}">'
        f'<div class="hd"><span class="lang">{name}</span>'
        f'<span class="badge">{badge}</span></div>'
        f'{body}'
        f'<div class="meta">{meta}{note_html}{credit_html}</div>'
        f'</div>'
    )


def render_page(results: List[Result]) -> str:
    ordered = sorted(
        results,
        key=lambda r: (_ORDER.get(r.status, 9), 0 if r.matched else 1, r.name.lower()),
    )
    tiles = "\n".join(_tile(r) for r in ordered)

    live = sum(1 for r in results if r.status == STATUS_SUCCESS)
    failed = sum(1 for r in results if r.status == STATUS_FAILED)
    na = sum(1 for r in results if r.status == STATUS_UNAVAILABLE)
    total = len(results)
    stats = (f"{total} languages &nbsp;•&nbsp; "
             f"<b class='s-ok'>{live} live</b> &nbsp;•&nbsp; "
             f"<b class='s-err'>{failed} failed</b> &nbsp;•&nbsp; "
             f"<b class='s-na'>{na} unavailable</b>")

    return (
        _TEMPLATE
        .replace("__STATS__", stats)
        .replace("__TILES__", tiles)
    )


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wall of Hello World</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; }
  body {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #05060a;
    color: #e7ecf5;
    min-height: 100vh;
    overflow-x: hidden;
  }
  body::before {
    content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background:
      radial-gradient(60vw 60vw at 12% 8%, rgba(56,189,248,.16), transparent 60%),
      radial-gradient(55vw 55vw at 88% 18%, rgba(168,85,247,.16), transparent 60%),
      radial-gradient(70vw 70vw at 50% 110%, rgba(34,197,94,.12), transparent 60%);
    animation: drift 24s ease-in-out infinite alternate;
  }
  @keyframes drift { from { transform: translate3d(0,0,0); } to { transform: translate3d(0,-2%,0) scale(1.04); } }

  header {
    position: sticky; top: 0; z-index: 5;
    padding: 16px 22px;
    background: linear-gradient(180deg, rgba(5,6,10,.96), rgba(5,6,10,.65));
    backdrop-filter: blur(6px);
    border-bottom: 1px solid rgba(255,255,255,.06);
  }
  header h1 {
    margin: 0; font-size: clamp(18px, 2.4vw, 30px); letter-spacing: .14em;
    font-weight: 800;
    background: linear-gradient(90deg, #38bdf8, #a855f7, #22c55e);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  header .stats { margin-top: 6px; font-size: 13px; color: #9aa6b8; }
  .s-ok { color: #4ade80; } .s-err { color: #fbbf24; } .s-na { color: #6b7280; }

  main {
    position: relative; z-index: 1;
    padding: 22px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px;
    align-content: start;
    min-height: calc(100vh - 84px);
  }

  .tile {
    position: relative; border-radius: 14px; padding: 14px 14px 12px;
    background: rgba(255,255,255,.035);
    border: 1px solid rgba(255,255,255,.08);
    display: flex; flex-direction: column; gap: 10px;
    min-height: 124px;
    animation: pop .5s ease both;
  }
  @keyframes pop { from { opacity: 0; transform: translateY(8px) scale(.98); } to { opacity: 1; transform: none; } }
  .tile .hd { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .tile .lang { font-size: 13px; font-weight: 700; letter-spacing: .03em; color: #cdd6e6; }
  .tile .badge {
    font-size: 10px; font-weight: 700; letter-spacing: .08em;
    padding: 2px 7px; border-radius: 999px; border: 1px solid transparent;
  }
  .tile .out {
    font-size: clamp(15px, 1.5vw, 20px); font-weight: 700; line-height: 1.25;
    word-break: break-word; flex: 1;
  }
  .tile .out.muted { color: #6b7280; font-weight: 600; }
  .tile .meta {
    display: flex; flex-direction: column; gap: 3px;
    font-size: 10.5px; color: #7c899e;
  }
  .tile .meta code { color: #8aa0bd; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tile .meta .note { color: #6b7686; font-style: italic; }
  .tile .meta .credit { color: #94a3b8; font-style: italic; font-size: 10px; opacity: .85; }
  .tile.ok .credit { color: #a7d4b5; }
  .tile .errlog { font-size: 10.5px; color: #d28b8b; white-space: pre-wrap; max-height: 48px; overflow: hidden; }
  .tile .out.err-text { color: #fbbf24; font-size: 15px; }

  .tile.ok { box-shadow: 0 0 0 1px rgba(34,197,94,.20), 0 10px 30px -18px rgba(34,197,94,.6); }
  .tile.ok .out { color: #c7f9d6; text-shadow: 0 0 18px rgba(34,197,94,.35); }
  .tile.ok .badge { color: #4ade80; border-color: rgba(74,222,128,.4); background: rgba(34,197,94,.10); }
  .tile.err { box-shadow: 0 0 0 1px rgba(251,191,36,.18); }
  .tile.err .badge { color: #fbbf24; border-color: rgba(251,191,36,.4); background: rgba(251,191,36,.08); }
  .tile.na { opacity: .62; }
  .tile.na .badge { color: #9ca3af; border-color: rgba(156,163,175,.35); background: rgba(156,163,175,.08); }

  /* centre button */
  #end-wrap {
    position: fixed; inset: 0; z-index: 50; pointer-events: none;
    display: flex; align-items: center; justify-content: center;
  }
  #end {
    pointer-events: auto; cursor: pointer; user-select: none;
    font-family: inherit; font-weight: 800; letter-spacing: .18em;
    font-size: clamp(16px, 2vw, 22px);
    color: #fff; padding: 22px 42px; border-radius: 16px; border: none;
    background: linear-gradient(135deg, #ef4444, #b91c1c);
    box-shadow: 0 0 0 6px rgba(239,68,68,.12), 0 18px 50px -12px rgba(239,68,68,.7);
    transition: transform .12s ease, box-shadow .2s ease;
    animation: pulse 2.4s ease-in-out infinite;
  }
  #end:hover { transform: scale(1.05); }
  #end:active { transform: scale(.97); }
  @keyframes pulse {
    0%,100% { box-shadow: 0 0 0 6px rgba(239,68,68,.12), 0 18px 50px -12px rgba(239,68,68,.7); }
    50%     { box-shadow: 0 0 0 14px rgba(239,68,68,.04), 0 18px 60px -8px rgba(239,68,68,.95); }
  }

  #ended {
    position: fixed; inset: 0; z-index: 100; display: none;
    align-items: center; justify-content: center; flex-direction: column; gap: 10px;
    background: rgba(3,4,8,.92); backdrop-filter: blur(8px); text-align: center;
  }
  #ended h2 { font-size: clamp(22px, 3vw, 40px); margin: 0;
    background: linear-gradient(90deg, #38bdf8, #22c55e); -webkit-background-clip: text; background-clip: text; color: transparent; }
  #ended p { color: #9aa6b8; margin: 0; }
</style>
</head>
<body>
  <header>
    <h1>WALL OF HELLO WORLD</h1>
    <div class="stats">__STATS__ &nbsp;•&nbsp; click <b>END PROJECT</b> to shut everything down</div>
  </header>

  <main>
    __TILES__
  </main>

  <div id="end-wrap">
    <button id="end" type="button">END PROJECT</button>
  </div>

  <div id="ended">
    <h2>Demonstration ended</h2>
    <p>The controller has shut down. No processes are running. You can close this window.</p>
  </div>

  <script>
    // Prove the HTML/JS tile really executes in this page.
    var jsTile = document.getElementById('browser-js');
    if (jsTile) { jsTile.textContent = ['Hello', 'World'].join(' '); }

    var ended = document.getElementById('ended');
    var btn = document.getElementById('end');
    btn.addEventListener('click', function () {
      btn.disabled = true;
      ended.style.display = 'flex';
      fetch('/exit').catch(function () {}).finally(function () {
        // Close the window if the browser allows it (app/kiosk windows do).
        setTimeout(function () { try { window.close(); } catch (e) {} }, 250);
      });
    });
  </script>
</body>
</html>
"""

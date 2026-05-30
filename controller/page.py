"""Renders an empty wall of placeholder tiles and ships the JS that fills
them in live as Server-Sent Events arrive from /events.

The initial HTML is fully self-contained (no external assets, no network)
and is held in memory by the server. The page subscribes to /events on load
and updates each tile in place when its language's result is published.
"""

import html
from typing import List

from .languages import Lang
from .portable import slug


def _placeholder(lang: Lang) -> str:
    s = slug(lang.name)
    name = html.escape(lang.name)
    note = html.escape(lang.note) if lang.note else ""
    note_html = f'<span class="note">{note}</span>' if note else ""
    credit_parts = []
    if lang.creator:
        credit_parts.append(f"by {html.escape(lang.creator)}")
    if lang.since:
        credit_parts.append(html.escape(lang.since))
    credit = " · ".join(credit_parts)
    credit_html = f'<span class="credit">{credit}</span>' if credit else ""
    return (
        f'<div class="tile loading" data-slug="{s}">'
        f'<div class="hd"><span class="lang">{name}</span>'
        f'<span class="badge">…</span></div>'
        f'<div class="out muted">running…</div>'
        f'<div class="meta">{note_html}{credit_html}</div>'
        f'</div>'
    )


def render_initial(langs: List[Lang]) -> str:
    tiles = "\n".join(_placeholder(l) for l in langs)
    return (_TEMPLATE
            .replace("__TILES__", tiles)
            .replace("__TOTAL__", str(len(langs))))


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
    background: #05060a; color: #e7ecf5; min-height: 100vh; overflow-x: hidden;
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
  header .progress { display: inline-block; width: 110px; height: 6px;
    background: rgba(255,255,255,.08); border-radius: 999px; overflow: hidden; vertical-align: middle; margin-left: 6px; }
  header .progress .bar { height: 100%; width: 0%; background: linear-gradient(90deg, #38bdf8, #22c55e); transition: width .25s ease; }
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
    transition: box-shadow .25s ease, transform .25s ease, opacity .3s ease;
  }
  .tile.loading { opacity: .55; animation: pulse-load 1.6s ease-in-out infinite; }
  @keyframes pulse-load { 0%, 100% { opacity: .55; } 50% { opacity: 0.9; } }
  .tile.flash { transform: scale(1.03); box-shadow: 0 0 0 1px rgba(56,189,248,.35), 0 12px 30px -16px rgba(56,189,248,.6); }
  .tile .hd { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .tile .lang { font-size: 13px; font-weight: 700; letter-spacing: .03em; color: #cdd6e6; }
  .tile .badge {
    font-size: 10px; font-weight: 700; letter-spacing: .08em;
    padding: 2px 7px; border-radius: 999px; border: 1px solid transparent;
    color: #6b7280; background: rgba(156,163,175,.08);
  }
  .tile .out {
    font-size: clamp(14px, 1.4vw, 18px); font-weight: 700; line-height: 1.25;
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

  .tile.ok { box-shadow: 0 0 0 1px rgba(34,197,94,.20), 0 10px 30px -18px rgba(34,197,94,.6); animation: none; opacity: 1; }
  .tile.ok .out { color: #c7f9d6; text-shadow: 0 0 18px rgba(34,197,94,.35); }
  .tile.ok .badge { color: #4ade80; border-color: rgba(74,222,128,.4); background: rgba(34,197,94,.10); }
  .tile.err { box-shadow: 0 0 0 1px rgba(251,191,36,.18); animation: none; opacity: 1; }
  .tile.err .badge { color: #fbbf24; border-color: rgba(251,191,36,.4); background: rgba(251,191,36,.08); }
  .tile.na { opacity: .62; animation: none; }
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
    <div class="stats">
      <span id="s-done">0</span>/<span id="s-total">__TOTAL__</span> done
      <span class="progress"><span class="bar" id="s-bar"></span></span>
      &nbsp;·&nbsp; <b class="s-ok"><span id="s-ok">0</span> live</b>
      &nbsp;·&nbsp; <b class="s-err"><span id="s-err">0</span> failed</b>
      &nbsp;·&nbsp; <b class="s-na"><span id="s-na">0</span> n/a</b>
      &nbsp;·&nbsp; click <b>END PROJECT</b> to shut everything down
    </div>
  </header>

  <main id="grid">
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
    const TOTAL = parseInt(document.getElementById('s-total').textContent, 10);
    const STATS = { ok: 0, fail: 0, na: 0 };
    const SEEN = new Set();

    function escapeHtml(s){
      if (s == null) return "";
      return String(s).replace(/[&<>"']/g, c => (
        {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]
      ));
    }

    function bumpStats(bucket){
      STATS[bucket] += 1;
      document.getElementById('s-ok').textContent = STATS.ok;
      document.getElementById('s-err').textContent = STATS.fail;
      document.getElementById('s-na').textContent = STATS.na;
      const done = STATS.ok + STATS.fail + STATS.na;
      document.getElementById('s-done').textContent = done;
      document.getElementById('s-bar').style.width = (100 * done / TOTAL).toFixed(1) + '%';
    }

    function flash(tile){
      tile.classList.add('flash');
      setTimeout(() => tile.classList.remove('flash'), 400);
    }

    function renderTile(tile, r){
      let badge, statusCls, body, metaCmd;
      const isBrowser = (r.name === 'HTML / JavaScript');

      if (r.status === 'success') {
        statusCls = 'ok'; badge = 'LIVE';
        if (isBrowser) {
          // Self-prove client-side: only a real JS engine in this page can write this.
          const ua = navigator.userAgent.match(/(Chrome|Safari|Firefox|Edg)\\/[\\d.]+/);
          const tag = ua ? ua[0] : 'browser';
          body = `<div class="out">Hello World — JavaScript in ${escapeHtml(tag)}</div>`;
        } else {
          body = `<div class="out">${escapeHtml(r.output) || 'Hello World'}</div>`;
        }
        const bytes = (r.output || '').length;
        metaCmd = `<code title="${escapeHtml(r.command)}">${escapeHtml(r.command)}</code>`
                + `<span>${r.elapsed_ms} ms · ${bytes} B</span>`;
      } else if (r.status === 'unavailable') {
        statusCls = 'na'; badge = 'N/A';
        if (r.missing && r.missing.length) {
          body = `<div class="out muted">runtime not installed</div>`;
          metaCmd = `<code>missing: ${escapeHtml(r.missing.join(', '))}</code>`;
        } else {
          body = `<div class="out muted">${escapeHtml(r.error || 'unavailable')}</div>`;
          metaCmd = '';
        }
      } else { // failed
        statusCls = 'err'; badge = 'FAIL';
        body = `<div class="out err-text">${escapeHtml(r.error || 'failed')}</div>`;
        if (r.output) body += `<div class="errlog">${escapeHtml(String(r.output).slice(0,300))}</div>`;
        metaCmd = `<code>${escapeHtml(r.command)}</code><span>${r.elapsed_ms} ms</span>`;
      }

      const note = r.note ? `<span class="note">${escapeHtml(r.note)}</span>` : '';
      const creditParts = [];
      if (r.creator) creditParts.push('by ' + r.creator);
      if (r.since) creditParts.push(r.since);
      const credit = creditParts.length
        ? `<span class="credit">${escapeHtml(creditParts.join(' · '))}</span>` : '';

      tile.className = `tile ${statusCls}`;
      tile.innerHTML = `
        <div class="hd"><span class="lang">${escapeHtml(r.name)}</span>
          <span class="badge">${badge}</span></div>
        ${body}
        <div class="meta">${metaCmd}${note}${credit}</div>
      `;

      if (!SEEN.has(r.slug)) {
        SEEN.add(r.slug);
        bumpStats(statusCls === 'ok' ? 'ok' : statusCls === 'na' ? 'na' : 'fail');
        flash(tile);
      }
    }

    // Subscribe to per-language results as they complete.
    const es = new EventSource('/events');
    es.addEventListener('result', e => {
      const r = JSON.parse(e.data);
      const tile = document.querySelector(`.tile[data-slug="${r.slug}"]`);
      if (tile) renderTile(tile, r);
    });
    es.addEventListener('done', e => {
      document.body.classList.add('all-done');
      es.close();
    });

    // END PROJECT button → /exit, then attempt window.close().
    const ended = document.getElementById('ended');
    const btn = document.getElementById('end');
    btn.addEventListener('click', () => {
      btn.disabled = true;
      ended.style.display = 'flex';
      try { es.close(); } catch(_) {}
      fetch('/exit').catch(() => {}).finally(() => {
        setTimeout(() => { try { window.close(); } catch (e) {} }, 250);
      });
    });
  </script>
</body>
</html>
"""

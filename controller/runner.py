"""Runs each language exactly once, captures the result, and never leaves
anything running.

Safety model:
  * every subprocess is launched in its own session (start_new_session=True)
    so the whole process tree can be killed as a group on timeout;
  * every step has a wall-clock timeout;
  * compiled artefacts live in a private temp dir that the caller deletes;
  * nothing is run through a shell, so there is no shell-injection surface.
"""

import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .languages import Lang
from .portable import (current_platform, exe_suffix, kill_tree,
                       popen_isolation_kwargs)

DEFAULT_TIMEOUT = 25.0          # seconds, per build step and per run
MAX_PARALLEL = 8                # be polite to the machine
MAX_OUTPUT_CHARS = 4000         # trim captured text for display

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_UNAVAILABLE = "unavailable"


@dataclass
class Result:
    name: str
    status: str                          # success | failed | unavailable
    output: str = ""                     # captured stdout (or stderr fallback)
    command: str = ""                    # the run command, for display
    error: str = ""                      # error / reason text
    elapsed_ms: int = 0
    category: str = "easy"
    note: str = ""
    matched: bool = False                # did output actually contain hello world
    real: bool = True                    # real execution vs. browser/simulated
    missing: List[str] = field(default_factory=list)  # absent executables
    creator: str = ""                    # historical attribution (from Lang)
    since: str = ""                      # year of first public release


def _trim(text: str) -> str:
    text = text.strip()
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return text


def _resolve(tokens: List[str], subst: Dict[str, str]) -> List[str]:
    return [tok.format(**subst) for tok in tokens]


def _run_capture(cmd: List[str], cwd: str, timeout: float):
    """Run argv, return (returncode, stdout, stderr, timed_out).

    On timeout the entire process tree is killed via the portable helper
    (process group on POSIX, `taskkill /F /T` on Windows) so no grandchild
    survives.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_isolation_kwargs(),
        )
    except FileNotFoundError as exc:
        return None, "", f"executable not found: {exc}", False
    except OSError as exc:
        return None, "", f"could not launch: {exc}", False

    try:
        out, err = proc.communicate(timeout=timeout)
        return (
            proc.returncode,
            out.decode("utf-8", "replace"),
            err.decode("utf-8", "replace"),
            False,
        )
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return None, "", f"timed out after {timeout:g}s", True


def execute(lang: Lang, root: str, default_timeout: float) -> Result:
    """Run a single language and return its Result. Never raises."""
    timeout = lang.timeout or default_timeout

    # Browser languages don't shell out; the page renders them live.
    if lang.kind == "browser":
        return Result(
            name=lang.name, status=STATUS_SUCCESS, output="Hello World",
            command="(rendered in browser)", category=lang.category,
            note=lang.note, matched=True, real=True,
            creator=lang.creator, since=lang.since,
        )

    # Platform restriction: honest "requires macOS" instead of attempting
    # something we know can't work (e.g. Obj-C without Foundation on Linux).
    if lang.platforms and current_platform() not in lang.platforms:
        return Result(
            name=lang.name, status=STATUS_UNAVAILABLE,
            error=f"requires {' or '.join(lang.platforms)}",
            command="", category=lang.category, note=lang.note,
            real=True, creator=lang.creator, since=lang.since,
        )

    # Availability: every required executable must be on PATH.
    missing = [exe for exe in lang.checks if shutil.which(exe) is None]
    if missing:
        return Result(
            name=lang.name, status=STATUS_UNAVAILABLE,
            error="runtime not installed",
            command=" ".join(lang.run) if lang.run else "",
            category=lang.category, note=lang.note, real=True, missing=missing,
            creator=lang.creator, since=lang.since,
        )

    work = os.path.join(root, re.sub(r"[^A-Za-z0-9]+", "_", lang.name).strip("_"))
    os.makedirs(work, exist_ok=True)
    src_path = os.path.join(work, lang.file)
    exe_path = os.path.join(work, "prog" + exe_suffix())
    subst = {"src": src_path, "exe": exe_path, "dir": work}

    if lang.source:
        with open(src_path, "w", encoding="utf-8") as fh:
            fh.write(lang.source)

    start = time.perf_counter()

    # Build steps (compilers / assemblers).
    for step in lang.build:
        cmd = _resolve(step, subst)
        rc, out, err, timed_out = _run_capture(cmd, work, timeout)
        if timed_out or rc != 0:
            elapsed = int((time.perf_counter() - start) * 1000)
            reason = "build timed out" if timed_out else "build failed"
            return Result(
                name=lang.name, status=STATUS_FAILED, error=reason,
                output=_trim(err or out), command=" ".join(cmd),
                elapsed_ms=elapsed, category=lang.category, note=lang.note,
                real=True, creator=lang.creator, since=lang.since,
            )

    # Run step.
    run_cmd = _resolve(lang.run, subst)
    rc, out, err, timed_out = _run_capture(run_cmd, work, timeout)
    elapsed = int((time.perf_counter() - start) * 1000)
    display_cmd = " ".join(run_cmd)

    if timed_out:
        return Result(
            name=lang.name, status=STATUS_FAILED, error="timed out",
            command=display_cmd, elapsed_ms=elapsed, category=lang.category,
            note=lang.note, real=True,
            creator=lang.creator, since=lang.since,
        )

    captured = out.strip() or err.strip()
    matched = "hello world" in captured.lower()

    if rc == 0:
        return Result(
            name=lang.name, status=STATUS_SUCCESS, output=_trim(captured),
            command=display_cmd, elapsed_ms=elapsed, category=lang.category,
            note=lang.note, matched=matched, real=True,
            creator=lang.creator, since=lang.since,
        )

    return Result(
        name=lang.name, status=STATUS_FAILED,
        error=f"exit code {rc}", output=_trim(err or out),
        command=display_cmd, elapsed_ms=elapsed, category=lang.category,
        note=lang.note, real=True,
        creator=lang.creator, since=lang.since,
    )


def collect(langs: List[Lang], root: str, default_timeout: float,
            progress=None) -> List[Result]:
    """Run all languages in parallel; return results in the input order."""
    results: Dict[str, Result] = {}
    done = 0
    total = len(langs)
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(execute, lang, root, default_timeout): lang
                   for lang in langs}
        for fut in as_completed(futures):
            lang = futures[fut]
            try:
                results[lang.name] = fut.result()
            except Exception as exc:  # defensive: a runner bug must not abort the wall
                results[lang.name] = Result(
                    name=lang.name, status=STATUS_FAILED,
                    error=f"runner error: {exc}", category=lang.category,
                    note=lang.note, real=True,
                    creator=lang.creator, since=lang.since,
                )
            done += 1
            if progress:
                progress(done, total, results[lang.name])
    return [results[lang.name] for lang in langs]

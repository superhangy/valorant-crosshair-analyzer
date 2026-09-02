# Watchdog for run_backlog.py. Every CHECK_SEC: if backlog work remains and
# neither the driver nor an analysis subprocess is alive, relaunch the driver
# detached. Exits when all backlog videos have a complete engagements.csv.
# Safe to run alongside a live driver -- it idles until the driver dies.
#
# Start (detached, survives this terminal / SSH / Claude session dying):
#   nohup python backlog_watchdog.py > /dev/null 2>&1 &
# It logs to backlog_watchdog_log.txt. Re-running a second copy is harmless
# (lockfile guard). Stop it: delete backlog_watchdog.lock, or kill the pid.

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass  # pythonw.exe / Task Scheduler: no real stdout

REPO = Path(__file__).resolve().parent
LOG = REPO / "backlog_watchdog_log.txt"
LOCK = REPO / "backlog_watchdog.lock"
CHECK_SEC = 60

sys.path.insert(0, str(REPO))  # so `import run_backlog` works from any cwd
import run_backlog as rb  # reuse candidates() / ok() / SKIP_SLUGS

# Always relaunch the driver with a CONSOLE python (pythonw has no stdout, which
# crashes the child analysis scripts on their first print()).
PY = sys.executable
for a, b in (("pythonw.exe", "python.exe"), ("pythonw3", "python3")):
    if PY.endswith(a):
        cand = PY[: -len(a)] + b
        if Path(cand).exists():
            PY = cand
        break


_CREATE_NO_WINDOW = 0x08000000


def _run_hidden(cmd, timeout):
    """subprocess.run for a console helper, with NO flashing window."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # SW_HIDE (0)
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        creationflags=_CREATE_NO_WINDOW, startupinfo=si,
    )


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} [watchdog] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        pass  # pythonw.exe: sys.stdout is None
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def remaining():
    todo = []
    for vid, (path, slug) in rb.candidates().items():
        if slug in rb.SKIP_SLUGS:
            continue
        if rb.ok(REPO / f"engagements_{slug}"):
            continue
        todo.append(slug)
    return todo


def procs_alive():
    """(driver_alive, analysis_alive) via tasklist + WMIC cmdline match."""
    try:
        out = _run_hidden(
            ["wmic", "process", "where", "name='python.exe'", "get",
             "CommandLine", "/format:list"],
            timeout=30,
        ).stdout
    except Exception as e:
        log(f"proc check failed ({e}); assuming both alive to be safe")
        return True, True
    driver = "run_backlog.py" in out
    analysis = "analyze_crosshair_placement.py" in out
    return driver, analysis


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    try:
        out = _run_hidden(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=20,
        ).stdout
        return str(pid) in out
    except Exception:
        return True  # can't tell -> assume alive, don't steal the lock


def main():
    if LOCK.exists():
        try:
            old = LOCK.read_text().strip()
        except Exception:
            old = "?"
        if pid_alive(old):
            log(f"lockfile held by live pid {old}; another watchdog running. exit.")
            return
        log(f"stale lockfile (pid {old} dead) -> taking over")
    LOCK.write_text(str(os.getpid()))
    log(f"start (pid {os.getpid()}); check every {CHECK_SEC}s")
    try:
        while True:
            todo = remaining()
            if not todo:
                log("all backlog videos have a complete engagements.csv. done.")
                return
            driver, analysis = procs_alive()
            if not driver and not analysis:
                log(f"{len(todo)} videos left, driver+analysis both dead -> "
                    f"relaunching run_backlog.py")
                subprocess.Popen(
                    [PY, "run_backlog.py"],
                    cwd=str(REPO),
                    stdout=open(REPO / "backlog_run_stdout.txt", "a",
                               encoding="utf-8"),
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | _CREATE_NO_WINDOW,
                )
                time.sleep(CHECK_SEC)  # give it time to spin up before rechecking
            time.sleep(CHECK_SEC)
    finally:
        try:
            LOCK.unlink()
        except Exception:
            pass
        log("watchdog exiting")


if __name__ == "__main__":
    main()

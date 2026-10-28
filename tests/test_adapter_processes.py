"""Exercise real descendants, including one that ignores normal termination."""

import json
import os
import subprocess
import sys
import time

import pytest

from dota_items.workflow.processes import run_adapter


def adapter(tmp_path, *, parent_exits=False):
    ready, marker = tmp_path / "ready", tmp_path / "late-write"
    child = (
        "import signal,time;from pathlib import Path;"
        + ("signal.signal(signal.SIGTERM,signal.SIG_IGN);" if os.name != "nt" else "")
        + f"Path({str(ready)!r}).write_text('ready');time.sleep(4);"
        + f"Path({str(marker)!r}).write_text('leaked')"
    )
    launcher = tmp_path / "launcher.py"
    launcher.write_text(
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        + f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
        + f"while not Path({str(ready)!r}).exists(): time.sleep(0.01)\n"
        + ("" if parent_exits else "time.sleep(30)\n"),
        encoding="utf-8",
    )
    return [sys.executable, str(launcher)], ready, marker


@pytest.mark.parametrize("outcome", ["timeout", "cancel", "parent_success"])
def test_adapter_scope_cleans_descendants(tmp_path, monkeypatch, outcome):
    command, ready, marker = adapter(tmp_path, parent_exits=outcome == "parent_success")
    if outcome == "cancel":
        original = subprocess.Popen.wait
        interrupted = False

        def wait(process, timeout=None):
            nonlocal interrupted
            if timeout == 2 and not interrupted:
                deadline = time.monotonic() + 3
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                interrupted = True
                raise KeyboardInterrupt
            return original(process, timeout=timeout)

        monkeypatch.setattr(subprocess.Popen, "wait", wait)
    started = time.monotonic()
    with (tmp_path / "process.log").open("w") as log:
        if outcome == "parent_success":
            assert run_adapter(command, cwd=tmp_path, stdout=log, timeout=2) == 0
        else:
            with pytest.raises(
                KeyboardInterrupt if outcome == "cancel" else subprocess.TimeoutExpired
            ):
                run_adapter(command, cwd=tmp_path, stdout=log, timeout=2)
    assert ready.exists(), "Must exercise an actually started descendant"
    time.sleep(max(0, 4.5 - (time.monotonic() - started)))
    assert not marker.exists(), json.dumps({"outcome": outcome, "child_wrote_after_cleanup": True})


def test_exit_status_and_log_preserved(tmp_path):
    with (tmp_path / "process.log").open("w") as log:
        assert (
            run_adapter(
                [sys.executable, "-c", "print('adapter output');raise SystemExit(7)"],
                cwd=tmp_path,
                stdout=log,
                timeout=2,
            )
            == 7
        )
    assert "adapter output" in (tmp_path / "process.log").read_text()

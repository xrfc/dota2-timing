"""Own adapter process trees through completion, timeout and cancellation."""

import os
import signal
import subprocess
import time


class _WindowsJob:
    """Assign a suspended process before any adapter code can spawn children."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes as w

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", w.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", w.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", w.DWORD),
                ("SchedulingClass", w.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", w.DWORD),
                ("cntUsage", w.DWORD),
                ("th32ThreadID", w.DWORD),
                ("th32OwnerProcessID", w.DWORD),
                ("tpBasePri", w.LONG),
                ("tpDeltaPri", w.LONG),
                ("dwFlags", w.DWORD),
            ]

        self.ctypes, self.w, self.ThreadEntry = ctypes, w, ThreadEntry
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([w.LPVOID, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
            "Thread32First": ([w.HANDLE, ctypes.POINTER(ThreadEntry)], w.BOOL),
            "Thread32Next": ([w.HANDLE, ctypes.POINTER(ThreadEntry)], w.BOOL),
            "OpenThread": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "ResumeThread": ([w.HANDLE], w.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            getattr(self.api, name).argtypes = arguments
            getattr(self.api, name).restype = result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach_and_resume(self, process):
        c, api = self.ctypes, self.api
        if not api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise c.WinError(c.get_last_error())
        snapshot = api.CreateToolhelp32Snapshot(4, 0)  # SNAPTHREAD
        if snapshot == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            entry = self.ThreadEntry()
            entry.dwSize = c.sizeof(entry)
            valid = api.Thread32First(snapshot, c.byref(entry))
            while valid:
                if entry.th32OwnerProcessID == process.pid:
                    thread = api.OpenThread(2, False, entry.th32ThreadID)  # SUSPEND_RESUME
                    if not thread:
                        raise c.WinError(c.get_last_error())
                    try:
                        if api.ResumeThread(thread) == 0xFFFFFFFF:
                            raise c.WinError(c.get_last_error())
                    finally:
                        api.CloseHandle(thread)
                    return
                valid = api.Thread32Next(snapshot, c.byref(entry))
            raise OSError("Suspended adapter thread not found")
        finally:
            api.CloseHandle(snapshot)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _stop_group(pid, grace=1.0):
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_adapter(command, *, cwd, stdout, timeout):
    """Return an exit code; preserve TimeoutExpired/KeyboardInterrupt after cleanup.

    Adapters are trusted user programs. POSIX children that deliberately create
    a new session escape process groups; this is resource management, not isolation.
    """
    job = _WindowsJob() if os.name == "nt" else None
    process = None
    try:
        options = {"creationflags": 4} if job else {"start_new_session": True}
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **options,
        )
        if job:
            job.attach_and_resume(process)
        return process.wait(timeout=timeout)
    finally:
        if job:
            job.close()
        elif process is not None:
            _stop_group(process.pid)
        if process is not None:
            # Also handles a suspended Windows process when assignment failed.
            if process.poll() is None:
                process.kill()
            process.wait()

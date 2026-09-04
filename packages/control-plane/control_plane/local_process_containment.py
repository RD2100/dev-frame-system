"""Provider-neutral ownership for one local Windows process tree."""

from __future__ import annotations

import os
import subprocess


class WindowsJob:
    """Own one Windows process tree and terminate it when the job closes."""

    _CREATE_SUSPENDED = 0x00000004
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _TH32CS_SNAPTHREAD = 0x00000004
    _THREAD_SUSPEND_RESUME = 0x0002
    _RESUME_FAILED = 0xFFFFFFFF

    def __init__(self) -> None:
        self._handle: int | None = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes

        class _BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class _ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class _BasicAccountingInformation(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        class _ThreadEntry32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Thread32First.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ThreadEntry32),
        ]
        kernel32.Thread32First.restype = wintypes.BOOL
        kernel32.Thread32Next.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ThreadEntry32),
        ]
        kernel32.Thread32Next.restype = wintypes.BOOL
        kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel32.ResumeThread.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise OSError(error, "SetInformationJobObject failed")
        self._handle = int(handle)
        self._kernel32 = kernel32
        self._accounting_type = _BasicAccountingInformation
        self._thread_entry_type = _ThreadEntry32

    def suspended_creation_flag(self) -> int:
        return self._CREATE_SUSPENDED if self._handle is not None else 0

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if self._handle is None:
            return
        import ctypes
        from ctypes import wintypes

        # CPython exposes the native process handle on Windows; callers assign
        # the suspended root before resuming it.
        process_handle = wintypes.HANDLE(int(process._handle))  # noqa: SLF001
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def resume(self, process: subprocess.Popen[bytes]) -> None:
        if self._handle is None:
            return
        import ctypes

        snapshot = self._kernel32.CreateToolhelp32Snapshot(self._TH32CS_SNAPTHREAD, 0)
        invalid_handle = ctypes.c_void_p(-1).value
        if not snapshot or int(snapshot) == invalid_handle:
            raise OSError(ctypes.get_last_error(), "thread snapshot failed")
        thread_ids: list[int] = []
        try:
            entry = self._thread_entry_type()
            entry.dwSize = ctypes.sizeof(entry)
            found = bool(self._kernel32.Thread32First(snapshot, ctypes.byref(entry)))
            while found:
                if int(entry.th32OwnerProcessID) == int(process.pid):
                    thread_ids.append(int(entry.th32ThreadID))
                found = bool(self._kernel32.Thread32Next(snapshot, ctypes.byref(entry)))
        finally:
            self._kernel32.CloseHandle(snapshot)
        if len(thread_ids) != 1:
            raise OSError("suspended process primary thread was not unique")
        thread = self._kernel32.OpenThread(
            self._THREAD_SUSPEND_RESUME,
            False,
            thread_ids[0],
        )
        if not thread:
            raise OSError(ctypes.get_last_error(), "OpenThread failed")
        try:
            previous_suspend_count = int(self._kernel32.ResumeThread(thread))
            if previous_suspend_count == self._RESUME_FAILED:
                raise OSError(ctypes.get_last_error(), "ResumeThread failed")
            if previous_suspend_count != 1:
                raise OSError("ResumeThread returned an unexpected suspend count")
        finally:
            self._kernel32.CloseHandle(thread)

    def active_processes(self) -> int:
        if self._handle is None:
            return 0
        import ctypes

        accounting = self._accounting_type()
        if not self._kernel32.QueryInformationJobObject(
            self._handle,
            self._JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        ):
            raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
        return int(accounting.ActiveProcesses)

    def close(self) -> bool:
        if self._handle is None:
            return True
        handle = self._handle
        terminated = bool(self._kernel32.TerminateJobObject(handle, 1))
        all_processes_stopped = self._kernel32.WaitForSingleObject(handle, 5_000) == 0
        closed = bool(self._kernel32.CloseHandle(handle))
        if closed:
            self._handle = None
        return terminated and all_processes_stopped and closed

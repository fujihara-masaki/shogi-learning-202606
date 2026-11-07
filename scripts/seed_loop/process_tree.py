"""OS ownership for an isolated supervisor: Linux subreaper/pidfds, Windows Job."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROC_ROOT = Path('/proc')


class OwnershipUnavailable(OSError):
    """A pre-spawn ownership prerequisite failed, rather than cleanup failing."""
    def __init__(self, reason, message):
        self.reason = reason
        super().__init__(message)


def check_proc_identity():
    """/proc IDs must be usable by getpid/Popen/pidfd in this namespace."""
    def identity(path):
        try:
            raw = path.read_text()
            pid = int(raw.split(' ', 1)[0])
            fields = raw.rpartition(')')[2].split()
            start = int(fields[19])
            if pid <= 0 or start < 0:
                raise ValueError('invalid process identity')
            return pid, start
        except (OSError, ValueError, IndexError) as exc:
            raise OwnershipUnavailable('linux_proc_self_unavailable',
                                       'Cannot read a usable /proc self identity; validation child not started') from exc

    pid = os.getpid()
    own = identity(PROC_ROOT / 'self/stat')
    if own[0] != pid:
        raise OwnershipUnavailable('linux_proc_pid_namespace_mismatch',
                                   f'/proc self PID {own[0]} differs from getpid {pid}; validation child not started')
    try:
        status = (PROC_ROOT / 'self/status').read_text()
        line = next(line for line in status.splitlines() if line.startswith('NSpid:'))
        namespace_pids = [int(value) for value in line.split()[1:]]
        if not namespace_pids:
            raise ValueError('missing namespace PID')
    except (OSError, ValueError, StopIteration) as exc:
        raise OwnershipUnavailable('linux_proc_self_unavailable',
                                   'Cannot read /proc self NSpid; validation child not started') from exc
    if namespace_pids != [pid]:
        raise OwnershipUnavailable('linux_proc_pid_namespace_mismatch',
                                   '/proc NSpid indicates a different PID namespace; validation child not started')
    numeric = identity(PROC_ROOT / str(pid) / 'stat')
    if numeric != own:
        raise OwnershipUnavailable('linux_proc_self_inconsistent',
                                   '/proc numeric self reference differs from /proc/self; validation child not started')


class LinuxTree:
    def __init__(self):
        check_proc_identity()
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise OSError("Linux pidfd support is required")
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), "subreaper setup failed")
        self.root = None

    @staticmethod
    def info(pid):
        try:
            fields = (Path('/proc') / str(pid) / 'stat').read_text().rpartition(')')[2].split()
            return {"pid": int(pid), "ppid": int(fields[1]), "start_ticks": int(fields[19]),
                    "state": fields[0]}
        except (FileNotFoundError, ProcessLookupError):
            return None

    def descendants(self):
        table = {}
        for path in Path('/proc').iterdir():
            if path.name.isdecimal():
                item = self.info(int(path.name))
                if item is not None:
                    table[item['pid']] = item
        parents = {os.getpid()}
        owned = {}
        while True:
            added = {pid: p for pid, p in table.items() if pid not in parents and p['ppid'] in parents}
            if not added:
                break
            owned.update(added)
            parents.update(added)
        return owned

    def start(self, command, **kwargs):
        self.root = subprocess.Popen(command, shell=False, start_new_session=True, **kwargs)
        return self.root

    def identities(self):
        return [{k:v for k,v in p.items() if k != 'state'} for p in self.descendants().values()]

    def is_descendant(self, item):
        current = self.info(item['pid'])
        if current is None or current['start_ticks'] != item['start_ticks']:
            return False
        for _ in range(1024):
            if current['ppid'] == os.getpid():
                return True
            parent = self.info(current['ppid'])
            if parent is None or parent['start_ticks'] > current['start_ticks'] or parent['pid'] == current['pid']:
                return False
            current = parent
        return False

    def reap(self):
        if self.root is not None:
            self.root.poll()  # Preserve the real root exit code before reaping adopted orphans.
        for pid, item in self.descendants().items():
            if item['ppid'] == os.getpid() and (self.root is None or pid != self.root.pid):
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    def cleanup(self):
        # Re-enumeration captures detached/reparented children, including Playwright webServers.
        deadline = time.monotonic() + 8
        soft_until = time.monotonic() + 0.3
        while True:
            self.reap()
            owned = self.descendants()
            if not owned:
                # A /proc directory snapshot can miss a just-forked child. ECHILD is
                # the kernel's confirmation that the subreaper has no remaining tree.
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                    if self.root is not None and pid == self.root.pid:
                        self.root.returncode = os.waitstatus_to_exitcode(status)
                except ChildProcessError:
                    return True
            if time.monotonic() >= deadline:
                return False
            for pid, item in owned.items():
                if item['state'] == 'Z':
                    continue
                try:
                    fd = os.pidfd_open(pid)
                    try:
                        current = self.info(pid)
                        if current is not None and current['start_ticks'] == item['start_ticks'] and self.is_descendant(item):
                            signal.pidfd_send_signal(fd, signal.SIGTERM if time.monotonic() < soft_until else signal.SIGKILL)
                    finally:
                        os.close(fd)
                except ProcessLookupError:
                    pass
            time.sleep(0.02)

    def close(self):
        pass


class WindowsTree:
    def __init__(self):
        from ctypes import wintypes as w
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        class BasicLimits(ctypes.Structure):
            _fields_ = [('ProcessTime', ctypes.c_int64), ('JobTime', ctypes.c_int64),
                        ('Flags', w.DWORD), ('MinWorkingSet', ctypes.c_size_t),
                        ('MaxWorkingSet', ctypes.c_size_t), ('ActiveLimit', w.DWORD),
                        ('Affinity', ctypes.c_size_t), ('Priority', w.DWORD), ('Scheduling', w.DWORD)]
        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]
        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('Basic', BasicLimits), ('Io', IoCounters),
                        ('ProcessMemory', ctypes.c_size_t), ('JobMemory', ctypes.c_size_t),
                        ('PeakProcessMemory', ctypes.c_size_t), ('PeakJobMemory', ctypes.c_size_t)]
        class Accounting(ctypes.Structure):
            _fields_ = [('UserTime', ctypes.c_int64), ('KernelTime', ctypes.c_int64),
                        ('PeriodUser', ctypes.c_int64), ('PeriodKernel', ctypes.c_int64),
                        ('PageFaults', w.DWORD), ('Total', w.DWORD), ('Active', w.DWORD), ('Terminated', w.DWORD)]
        self.accounting = Accounting
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        self.root = None

    def start(self, command, **kwargs):
        # No child code runs before assignment, including on a fast controller exit.
        self.root = subprocess.Popen(command, shell=False,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x4, **kwargs)
        try:
            if not self.api.AssignProcessToJobObject(self.handle, int(self.root._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
            native = ctypes.WinDLL('ntdll')
            native.NtResumeProcess.argtypes = [ctypes.c_void_p]
            native.NtResumeProcess.restype = ctypes.c_long
            if native.NtResumeProcess(int(self.root._handle)) != 0:
                raise OSError("could not resume assigned process")
        except OSError:
            self.root.kill()
            self.root.wait(timeout=5)
            raise
        return self.root

    def identities(self):
        if self.root is None:
            return []
        from ctypes import wintypes as w
        self.api.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
        times = [w.FILETIME() for _ in range(4)]
        if not self.api.GetProcessTimes(int(self.root._handle), *(ctypes.byref(t) for t in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return [{"pid": self.root.pid, "creation_filetime": created,
                 "identity": "held process handle in non-breakaway Job"}]

    def reap(self):
        if self.root is not None:
            self.root.poll()

    def cleanup(self):
        if not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            info = self.accounting()
            if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.Active == 0:
                if self.root is not None:
                    self.root.wait(timeout=5)
                return True
            time.sleep(0.02)
        return False

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def owned_tree():
    if sys.platform == 'linux':
        return LinuxTree()
    if os.name == 'nt':
        return WindowsTree()
    raise OSError('owned-process supervision requires Linux pidfds/subreaper or Windows Job Objects')

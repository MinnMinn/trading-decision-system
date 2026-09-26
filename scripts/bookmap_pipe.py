"""Win32 named-pipe server for the H1 recorder, via ctypes (stdlib only; BMREC-32).

BMREC-11: explicit security descriptor (owner SID only, protected DACL), PIPE_ACCESS_INBOUND (BMREC-05),
FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_REJECT_REMOTE_CLIENTS, max instances = 1. The stdlib multiprocessing pipe
listener is never used: it creates the pipe with a NULL descriptor, unlimited instances, accepts remote clients and
unpickles (security review F9-F11).
BMREC-12: any creation failure raises PipeSquatted / PipeCreateError -- the caller exits; there is no retry under
another name and no connecting to an existing pipe.
BMREC-13: the client's PID, executable path and logon session are read from the kernel, not from the client.

Overlapped I/O keeps the recorder's single-threaded loop responsive: every wait has a timeout.
"""
import ctypes
import ctypes.wintypes as W
import os
import re

if os.name != "nt":  # pragma: no cover - the recorder is Windows-only by design (plan §0)
    raise ImportError("bookmap_pipe requires Windows")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)

PIPE_ACCESS_INBOUND = 0x00000001
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_TYPE_BYTE = 0x0
PIPE_READMODE_BYTE = 0x0
PIPE_WAIT = 0x0
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
MAX_INSTANCES = 1
IN_BUFFER = 65536

OPEN_MODE = PIPE_ACCESS_INBOUND | FILE_FLAG_FIRST_PIPE_INSTANCE | FILE_FLAG_OVERLAPPED
PIPE_MODE = PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_ACCESS_DENIED = 5
ERROR_BROKEN_PIPE = 109
ERROR_PIPE_BUSY = 231
ERROR_NO_DATA = 232
ERROR_MORE_DATA = 234
ERROR_PIPE_CONNECTED = 535
ERROR_OPERATION_ABORTED = 995
ERROR_IO_INCOMPLETE = 996
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102

TOKEN_QUERY = 0x0008
TokenUser, TokenStatistics, TokenElevation = 1, 10, 20
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SE_KERNEL_OBJECT = 6
OWNER_SECURITY_INFORMATION = 0x1
DACL_SECURITY_INFORMATION = 0x4
SDDL_REVISION_1 = 1

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", W.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", W.BOOL)]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t), ("Offset", W.DWORD),
                ("OffsetHigh", W.DWORD), ("hEvent", W.HANDLE)]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", W.DWORD), ("HighPart", W.LONG)]


class TOKEN_STATISTICS(ctypes.Structure):
    _fields_ = [("TokenId", LUID), ("AuthenticationId", LUID), ("ExpirationTime", ctypes.c_longlong),
                ("TokenType", ctypes.c_int), ("ImpersonationLevel", ctypes.c_int), ("DynamicCharged", W.DWORD),
                ("DynamicAvailable", W.DWORD), ("GroupCount", W.DWORD), ("PrivilegeCount", W.DWORD),
                ("ModifiedId", LUID)]


def _sig(fn, restype, *argtypes):
    fn.restype = restype
    fn.argtypes = list(argtypes)
    return fn


_sig(k32.CreateNamedPipeW, W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD,
     ctypes.POINTER(SECURITY_ATTRIBUTES))
_sig(k32.ConnectNamedPipe, W.BOOL, W.HANDLE, ctypes.POINTER(OVERLAPPED))
_sig(k32.DisconnectNamedPipe, W.BOOL, W.HANDLE)
_sig(k32.CreateEventW, W.HANDLE, ctypes.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR)
_sig(k32.ResetEvent, W.BOOL, W.HANDLE)
_sig(k32.WaitForSingleObject, W.DWORD, W.HANDLE, W.DWORD)
_sig(k32.GetOverlappedResult, W.BOOL, W.HANDLE, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(W.DWORD), W.BOOL)
_sig(k32.ReadFile, W.BOOL, W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.POINTER(OVERLAPPED))
_sig(k32.WriteFile, W.BOOL, W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p)
_sig(k32.CancelIoEx, W.BOOL, W.HANDLE, ctypes.POINTER(OVERLAPPED))
_sig(k32.CloseHandle, W.BOOL, W.HANDLE)
_sig(k32.GetCurrentProcess, W.HANDLE)
_sig(k32.OpenProcess, W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
_sig(k32.QueryFullProcessImageNameW, W.BOOL, W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD))
_sig(k32.GetNamedPipeClientProcessId, W.BOOL, W.HANDLE, ctypes.POINTER(W.ULONG))
_sig(k32.LocalFree, ctypes.c_void_p, ctypes.c_void_p)
_sig(k32.CreateFileW, W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE)
_sig(adv.OpenProcessToken, W.BOOL, W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE))
_sig(adv.GetTokenInformation, W.BOOL, W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD))
_sig(adv.ConvertSidToStringSidW, W.BOOL, ctypes.c_void_p, ctypes.POINTER(W.LPWSTR))
_sig(adv.ConvertStringSecurityDescriptorToSecurityDescriptorW, W.BOOL, W.LPCWSTR, W.DWORD,
     ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(W.ULONG))
_sig(adv.GetSecurityInfo, W.DWORD, W.HANDLE, ctypes.c_int, W.DWORD, ctypes.c_void_p, ctypes.c_void_p,
     ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_sig(adv.ConvertSecurityDescriptorToStringSecurityDescriptorW, W.BOOL, ctypes.c_void_p, W.DWORD, W.DWORD,
     ctypes.POINTER(W.LPWSTR), ctypes.POINTER(W.ULONG))


class PipeError(OSError):
    pass


class PipeSquatted(PipeError):
    """The name already exists (FIRST_PIPE_INSTANCE refused). BMREC-12: stop, never detour."""


class PipeCreateError(PipeError):
    pass


def _err():
    return ctypes.get_last_error()


# ---------------------------------------------------------------- tokens and identities


def _token_info(token, cls):
    need = W.DWORD(0)
    adv.GetTokenInformation(token, cls, None, 0, ctypes.byref(need))
    buf = ctypes.create_string_buffer(max(need.value, 1))
    if not adv.GetTokenInformation(token, cls, buf, need, ctypes.byref(need)):
        raise PipeError(f"GetTokenInformation({cls}) failed: {_err()}")
    return buf


def _process_token(hproc):
    tok = W.HANDLE()
    if not adv.OpenProcessToken(hproc, TOKEN_QUERY, ctypes.byref(tok)):
        raise PipeError(f"OpenProcessToken failed: {_err()}")
    return tok


def _sid_string(token):
    buf = _token_info(token, TokenUser)
    psid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
    s = W.LPWSTR()
    if not adv.ConvertSidToStringSidW(psid, ctypes.byref(s)):
        raise PipeError(f"ConvertSidToStringSid failed: {_err()}")
    try:
        return s.value
    finally:
        k32.LocalFree(s)


def _auth_id(token):
    st = TOKEN_STATISTICS.from_buffer_copy(_token_info(token, TokenStatistics).raw[:ctypes.sizeof(TOKEN_STATISTICS)])
    return (st.AuthenticationId.HighPart, st.AuthenticationId.LowPart)


def current_user_sid():
    tok = _process_token(k32.GetCurrentProcess())
    try:
        return _sid_string(tok)
    finally:
        k32.CloseHandle(tok)


def current_logon_id():
    tok = _process_token(k32.GetCurrentProcess())
    try:
        return _auth_id(tok)
    finally:
        k32.CloseHandle(tok)


def is_elevated():
    """BMREC-09: the recorder refuses to run elevated."""
    tok = _process_token(k32.GetCurrentProcess())
    try:
        return bool(ctypes.cast(_token_info(tok, TokenElevation), ctypes.POINTER(W.DWORD))[0])
    finally:
        k32.CloseHandle(tok)


def process_identity(pid):
    """(image_path, user_sid, logon_id) for a PID, read from the kernel. Raises PipeError if unreadable."""
    hp = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not hp:
        raise PipeError(f"OpenProcess({pid}) failed: {_err()}")
    try:
        size = W.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not k32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(size)):
            raise PipeError(f"QueryFullProcessImageName failed: {_err()}")
        tok = _process_token(hp)
        try:
            return buf.value, _sid_string(tok), _auth_id(tok)
        finally:
            k32.CloseHandle(tok)
    finally:
        k32.CloseHandle(hp)


def owner_only_sddl(sid):
    """Protected DACL with a single ACE: full access for the owner's SID. Nothing for Everyone, Anonymous,
    NETWORK, Authenticated Users, Users, SYSTEM or Administrators (BMREC-11)."""
    return f"O:{sid}D:P(A;;GA;;;{sid})"


# ---------------------------------------------------------------- the server


class SecurePipeServer:
    def __init__(self, name):
        self.name = name
        self.sid = current_user_sid()
        psd = ctypes.c_void_p()
        if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(owner_only_sddl(self.sid), SDDL_REVISION_1,
                                                                         ctypes.byref(psd), None):
            raise PipeCreateError(f"cannot build security descriptor: {_err()}")
        self._psd = psd
        sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), psd, False)
        h = k32.CreateNamedPipeW(name, OPEN_MODE, PIPE_MODE, MAX_INSTANCES, 0, IN_BUFFER, 0, ctypes.byref(sa))
        if h in (None, 0, INVALID_HANDLE_VALUE):
            e = _err()
            k32.LocalFree(psd)
            if e in (ERROR_ACCESS_DENIED, ERROR_PIPE_BUSY):
                raise PipeSquatted(f"pipe name already exists (error {e})")
            raise PipeCreateError(f"CreateNamedPipe failed: {e}")
        self.h = h
        self.ev = k32.CreateEventW(None, True, False, None)
        self.ov = OVERLAPPED()
        self.ov.hEvent = self.ev
        self.buf = ctypes.create_string_buffer(IN_BUFFER)
        self.pending = None  # None | "connect" | "read"
        self.connected = False

    # -- introspection for tests / evidence
    def dacl_sddl(self):
        psd = ctypes.c_void_p()
        rc = adv.GetSecurityInfo(self.h, SE_KERNEL_OBJECT, DACL_SECURITY_INFORMATION | OWNER_SECURITY_INFORMATION,
                                 None, None, None, None, ctypes.byref(psd))
        if rc != 0:
            raise PipeError(f"GetSecurityInfo failed: {rc}")
        s = W.LPWSTR()
        try:
            if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    psd, SDDL_REVISION_1, DACL_SECURITY_INFORMATION | OWNER_SECURITY_INFORMATION,
                    ctypes.byref(s), None):
                raise PipeError(f"ConvertSecurityDescriptorToString failed: {_err()}")
            return s.value
        finally:
            if s:
                k32.LocalFree(s)
            k32.LocalFree(psd)

    def _reset(self):
        k32.ResetEvent(self.ev)
        self.ov.Internal = self.ov.InternalHigh = 0
        self.ov.Offset = self.ov.OffsetHigh = 0

    def wait_connect(self, timeout_ms):
        """True once a client is connected. Never blocks longer than timeout_ms."""
        if self.connected:
            return True
        if self.pending is None:
            self._reset()
            ok = k32.ConnectNamedPipe(self.h, ctypes.byref(self.ov))
            e = _err()
            if ok or e == ERROR_PIPE_CONNECTED:
                self.connected = True
                return True
            if e != ERROR_IO_PENDING:
                raise PipeError(f"ConnectNamedPipe failed: {e}")
            self.pending = "connect"
        if k32.WaitForSingleObject(self.ev, timeout_ms) == WAIT_TIMEOUT:
            return False
        n = W.DWORD(0)
        self.pending = None
        if not k32.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(n), False):
            raise PipeError(f"ConnectNamedPipe completion failed: {_err()}")
        self.connected = True
        return True

    def client_pid(self):
        pid = W.ULONG(0)
        if not k32.GetNamedPipeClientProcessId(self.h, ctypes.byref(pid)):
            raise PipeError(f"GetNamedPipeClientProcessId failed: {_err()}")
        return pid.value

    def read(self, timeout_ms):
        """bytes (possibly empty on timeout) or None when the client has gone (EOF/broken pipe)."""
        if not self.connected:
            return None
        if self.pending is None:
            self._reset()
            n = W.DWORD(0)
            ok = k32.ReadFile(self.h, self.buf, IN_BUFFER, ctypes.byref(n), ctypes.byref(self.ov))
            e = _err()
            if not ok:
                if e == ERROR_IO_PENDING:
                    self.pending = "read"
                elif e in (ERROR_BROKEN_PIPE, ERROR_NO_DATA, ERROR_OPERATION_ABORTED):
                    return None
                elif e != ERROR_MORE_DATA:
                    raise PipeError(f"ReadFile failed: {e}")
            if self.pending is None:
                got = W.DWORD(0)
                if not k32.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(got), False):
                    e = _err()
                    if e in (ERROR_BROKEN_PIPE, ERROR_NO_DATA, ERROR_OPERATION_ABORTED):
                        return None
                    if e != ERROR_MORE_DATA:
                        raise PipeError(f"ReadFile result failed: {e}")
                return self.buf.raw[:got.value]
        if k32.WaitForSingleObject(self.ev, timeout_ms) == WAIT_TIMEOUT:
            return b""
        self.pending = None
        got = W.DWORD(0)
        if not k32.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(got), False):
            e = _err()
            if e in (ERROR_BROKEN_PIPE, ERROR_NO_DATA, ERROR_OPERATION_ABORTED):
                return None
            if e != ERROR_MORE_DATA:
                raise PipeError(f"ReadFile completion failed: {e}")
        return self.buf.raw[:got.value]

    def _cancel_pending(self):
        if self.pending is not None:
            k32.CancelIoEx(self.h, ctypes.byref(self.ov))
            n = W.DWORD(0)
            k32.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(n), True)
            self.pending = None

    def disconnect(self):
        """Drop the current client and keep the (single) instance to listen again -- the name is never released
        while the recorder runs, so it cannot be squatted between sessions."""
        self._cancel_pending()
        k32.DisconnectNamedPipe(self.h)
        self.connected = False

    def close(self):
        if getattr(self, "h", None):
            self._cancel_pending()
            k32.DisconnectNamedPipe(self.h)
            k32.CloseHandle(self.h)
            self.h = None
        if getattr(self, "ev", None):
            k32.CloseHandle(self.ev)
            self.ev = None
        if getattr(self, "_psd", None):
            k32.LocalFree(self._psd)
            self._psd = None


# ---------------------------------------------------------------- BMREC-19: the recording root's ACL

SE_FILE_OBJECT = 1
_sig(k32.CreateDirectoryW, W.BOOL, W.LPCWSTR, ctypes.POINTER(SECURITY_ATTRIBUTES))
_sig(adv.GetNamedSecurityInfoW, W.DWORD, W.LPCWSTR, ctypes.c_int, W.DWORD, ctypes.c_void_p, ctypes.c_void_p,
     ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))

OTHER_TRUSTEES = ("WD", "AU", "BU", "AN", "IU", "NU", "S-1-1-0", "S-1-5-11", "S-1-5-32-545", "S-1-5-7", "S-1-5-4",
                  "S-1-5-2")
_WRITE_TOKENS = {"GA", "GW", "FA", "FW", "WD", "WP", "WO", "SD", "DC", "CC"}
_WRITE_MASK = 0x10000000 | 0x40000000 | 0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000


def private_dir_sddl(sid):
    """Owner + SYSTEM + Administrators, inherited by children; nothing for any other principal (BMREC-19)."""
    return f"O:{sid}D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"


def create_private_dir(path):
    """Create ONE directory with the private DACL. Parents must already exist. Raises PipeError on failure."""
    psd = ctypes.c_void_p()
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(private_dir_sddl(current_user_sid()),
                                                                     SDDL_REVISION_1, ctypes.byref(psd), None):
        raise PipeError(f"cannot build directory security descriptor: {_err()}")
    try:
        sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), psd, False)
        if not k32.CreateDirectoryW(path, ctypes.byref(sa)):
            raise PipeError(f"CreateDirectory failed: {_err()}")
    finally:
        k32.LocalFree(psd)


def path_dacl_sddl(path):
    psd = ctypes.c_void_p()
    rc = adv.GetNamedSecurityInfoW(path, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, None, None, None, None,
                                   ctypes.byref(psd))
    if rc != 0:
        raise PipeError(f"GetNamedSecurityInfo failed: {rc}")
    s = W.LPWSTR()
    try:
        if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(psd, SDDL_REVISION_1,
                                                                       DACL_SECURITY_INFORMATION, ctypes.byref(s),
                                                                       None):
            raise PipeError(f"ConvertSecurityDescriptorToString failed: {_err()}")
        return s.value
    finally:
        if s:
            k32.LocalFree(s)
        k32.LocalFree(psd)


def others_with_write(sddl):
    """ACEs in an SDDL DACL that grant any write/delete/ownership right to a broad principal (Everyone,
    Authenticated Users, Users, Anonymous, Interactive, Network, ...). Empty list = acceptable."""
    dacl = sddl.split("D:", 1)[1] if "D:" in sddl else ""
    bad = []
    for ace in re.findall(r"\(([^)]*)\)", dacl):
        parts = ace.split(";")
        if len(parts) < 6 or parts[0] not in ("A", "OA"):
            continue
        rights, trustee = parts[2], parts[5]
        if trustee not in OTHER_TRUSTEES:
            continue
        if rights.lower().startswith("0x"):
            writes = int(rights, 16) & _WRITE_MASK
        else:
            writes = any(rights[i:i + 2] in _WRITE_TOKENS for i in range(0, len(rights), 2))
        if writes:
            bad.append(ace)
    return bad


# ---------------------------------------------------------------- test/fake client helpers


class PipeClient:
    """Minimal write-only client (tests and the Python fake add-on)."""

    def __init__(self, name, access=GENERIC_WRITE):
        h = k32.CreateFileW(name, access, 0, None, OPEN_EXISTING, 0, None)
        if h in (None, 0, INVALID_HANDLE_VALUE):
            e = PipeError(f"CreateFile failed: {_err()}")
            e.win_error = _err()
            raise e
        self.h = h

    def write(self, data):
        n = W.DWORD(0)
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        if not k32.WriteFile(self.h, buf, len(data), ctypes.byref(n), None):
            raise PipeError(f"WriteFile failed: {_err()}")
        return n.value

    def close(self):
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None


def create_squatter(name):
    """A plain named pipe with default security, used by tests to simulate squatting (BMREC-12)."""
    h = k32.CreateNamedPipeW(name, PIPE_ACCESS_INBOUND, PIPE_MODE, 1, 0, 4096, 0, None)
    if h in (None, 0, INVALID_HANDLE_VALUE):
        raise PipeError(f"squatter CreateNamedPipe failed: {_err()}")
    return h


def close_handle(h):
    k32.CloseHandle(h)

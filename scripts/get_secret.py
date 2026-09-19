#!/usr/bin/env python3
"""Read one named secret out of the operating system's own credential store.

    python3 scripts/get_secret.py <service> [account]      -> the secret on stdout, nothing else

Replaces scripts/get-secret.sh, which called macOS's `security find-generic-password`. That command does not
exist on Windows, and the platform moves there (docs/plans/2026-09-20-windows-migration.md). The reference
syntax stays exactly what CLAUDE.md already declares -- `keychain:<service>[@<account>]` -- so no registry,
env file or caller changes; only what answers the question changes.

Backends, chosen by platform and never guessed:
  * macOS   -- `security find-generic-password -a <account> -s <service> -w` (the login Keychain).
  * Windows -- Credential Manager, read through PowerShell's CredentialManager module if present, else
               `cmdkey`-stored generic credentials via the Win32 CredRead API through ctypes. No third-party
               package, because adding a dependency to the secret path is its own risk.
  * Linux   -- `secret-tool lookup service <service> account <account>` (libsecret), if installed.

Rules this file exists to keep (CLAUDE.md, config/env.example):
  * The secret goes to stdout and NOWHERE else. Never logged, never echoed, never in an exception message.
  * A missing secret EXITS NON-ZERO with a message naming the service and the store -- never an empty string,
    because an empty API key silently becomes an unauthenticated request rather than a refusal.
  * No fallback between stores. If this platform's store does not have it, that is the answer.
"""
import os
import platform
import subprocess
import sys


class SecretError(Exception):
    """Never carries the secret. Carries only what was asked for and where it was looked for."""


def _run(argv):
    try:
        r = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        return None, f"{argv[0]} is not installed"
    if r.returncode != 0:
        return None, (r.stderr or "").strip()[:200] or f"{argv[0]} exited {r.returncode}"
    return r.stdout.rstrip("\r\n"), None


def _macos(service, account):
    out, err = _run(["security", "find-generic-password", "-a", account, "-s", service, "-w"])
    if out is None:
        raise SecretError(f"macOS Keychain has no generic password for service {service!r} "
                          f"account {account!r} ({err})")
    return out


def _windows(service, account):
    target = f"{service}" if not account else f"{service}/{account}"
    # PowerShell + CredentialManager module, when the operator has installed it.
    ps = ("$ErrorActionPreference='Stop';"
          "if (Get-Module -ListAvailable -Name CredentialManager) {"
          f"  $c = Get-StoredCredential -Target '{target}';"
          "   if ($c) { [System.Net.NetworkCredential]::new('', $c.Password).Password } else { exit 3 }"
          "} else { exit 4 }")
    out, err = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps])
    if out:
        return out
    # Fall back to the Win32 credential store directly, so no module install is required.
    try:
        import ctypes
        from ctypes import wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                        ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wintypes.DWORD),
                        ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        advapi.CredReadW.restype = wintypes.BOOL
        ptr = ctypes.POINTER(CREDENTIAL)()
        if not advapi.CredReadW(target, 1, 0, ctypes.byref(ptr)):     # 1 = CRED_TYPE_GENERIC
            raise SecretError(f"Windows Credential Manager has no generic credential for target "
                              f"{target!r} (CredRead error {ctypes.get_last_error()})")
        try:
            blob = ctypes.string_at(ptr.contents.CredentialBlob, ptr.contents.CredentialBlobSize)
        finally:
            advapi.CredFree(ptr)
        return blob.decode("utf-16-le" if len(blob) % 2 == 0 else "utf-8").rstrip("\r\n")
    except SecretError:
        raise
    except Exception as exc:
        raise SecretError(f"Windows Credential Manager could not be read for target {target!r}: "
                          f"{type(exc).__name__} ({err or 'no PowerShell module'})") from None


def _linux(service, account):
    out, err = _run(["secret-tool", "lookup", "service", service, "account", account])
    if not out:
        raise SecretError(f"libsecret has no entry for service {service!r} account {account!r} ({err})")
    return out


BACKENDS = {"Darwin": _macos, "Windows": _windows, "Linux": _linux}


def get(service, account="binance-testnet"):
    """The secret, or raise. Never returns an empty string: an empty API key does not fail, it sends an
    unauthenticated request, which is the failure that looks like a venue problem."""
    system = platform.system()
    fn = BACKENDS.get(system)
    if fn is None:
        raise SecretError(f"no credential store is wired for platform {system!r} "
                          f"(have {sorted(BACKENDS)}); refusing rather than reading a secret from disk")
    value = fn(service, account)
    if not value:
        raise SecretError(f"the credential store returned an EMPTY value for service {service!r} "
                          f"account {account!r}; treating that as absent")
    return value


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    service = argv[0]
    account = argv[1] if len(argv) > 1 else "binance-testnet"
    try:
        sys.stdout.write(get(service, account))
    except SecretError as exc:
        print(str(exc), file=sys.stderr)      # the message never contains the secret
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

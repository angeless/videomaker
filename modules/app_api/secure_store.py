#!/usr/bin/env python3
"""Local secret storage abstraction (macOS Keychain first)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import os
import platform
import shutil
import subprocess


def _normalize_secret_name(name: str) -> str:
    raw = str(name or "").strip().lower()
    if not raw:
        return ""
    out = []
    for ch in raw:
        if ch.isalnum() or ch in {".", "_", "-"}:
            out.append(ch)
        else:
            out.append("_")
    token = "".join(out).strip("._-")
    return token[:128]


@dataclass(frozen=True)
class SecretStoreInfo:
    backend: str
    available: bool
    reason: str = ""


class SecretStore:
    def info(self) -> SecretStoreInfo:  # pragma: no cover - interface
        raise NotImplementedError

    def get(self, name: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def set(self, name: str, value: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, name: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def public_status(self) -> Dict[str, Any]:
        meta = self.info()
        return {
            "backend": meta.backend,
            "available": bool(meta.available),
            "reason": str(meta.reason or ""),
        }


class NullSecretStore(SecretStore):
    def __init__(self, reason: str = "unavailable"):
        self._info = SecretStoreInfo(backend="none", available=False, reason=str(reason or "unavailable"))

    def info(self) -> SecretStoreInfo:
        return self._info

    def get(self, name: str) -> str:
        _ = name
        return ""

    def set(self, name: str, value: str) -> bool:
        _ = name
        _ = value
        return False

    def delete(self, name: str) -> bool:
        _ = name
        return False


class KeychainSecretStore(SecretStore):
    def __init__(self, service_name: str = "videoeditor.ai"):
        self._service_name = str(service_name or "videoeditor.ai").strip() or "videoeditor.ai"
        self._info = SecretStoreInfo(backend="macos_keychain", available=True, reason="")

    def info(self) -> SecretStoreInfo:
        return self._info

    def _run(self, args: list[str], *, input_text: Optional[str] = None, timeout_s: float = 8.0) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )

    def get(self, name: str) -> str:
        key = _normalize_secret_name(name)
        if not key:
            return ""
        proc = self._run(
            [
                "security",
                "find-generic-password",
                "-a",
                key,
                "-s",
                self._service_name,
                "-w",
            ],
        )
        if proc.returncode != 0:
            return ""
        return str(proc.stdout or "").strip()

    def set(self, name: str, value: str) -> bool:
        key = _normalize_secret_name(name)
        secret = str(value or "").strip()
        if not key or not secret:
            return False
        proc = self._run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-a",
                key,
                "-s",
                self._service_name,
                "-w",
                secret,
            ],
        )
        return proc.returncode == 0

    def delete(self, name: str) -> bool:
        key = _normalize_secret_name(name)
        if not key:
            return False
        proc = self._run(
            [
                "security",
                "delete-generic-password",
                "-a",
                key,
                "-s",
                self._service_name,
            ],
        )
        if proc.returncode == 0:
            return True
        err = str(proc.stderr or "")
        # Treat "item not found" as success for idempotent cleanup.
        if "could not be found" in err.lower():
            return True
        return False


def build_secret_store(service_name: str = "videoeditor.ai") -> SecretStore:
    forced = str(os.environ.get("VIDEOEDITOR_SECRET_BACKEND", "") or "").strip().lower()
    if forced in {"none", "off", "disabled"}:
        return NullSecretStore("disabled_by_env")

    is_macos = platform.system().lower() == "darwin"
    has_security = bool(shutil.which("security"))
    if forced == "macos_keychain":
        if is_macos and has_security:
            return KeychainSecretStore(service_name=service_name)
        return NullSecretStore("macos_keychain_unavailable")

    if is_macos and has_security:
        return KeychainSecretStore(service_name=service_name)
    if not is_macos:
        return NullSecretStore("platform_not_macos")
    return NullSecretStore("security_cli_missing")


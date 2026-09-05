"""State isolation, snapshot fingerprinting, and hardened external side-effect blocking guards."""

from contextlib import contextmanager
import copy
import hashlib
import http.client
import json
import os
import socket
import subprocess
from typing import Any, Dict, List, Optional
from unittest.mock import patch
import urllib.request

from covenant.synthetic_data.store import (
    SyntheticWorkspaceStore,
    _current_workspace_store,
)


class ExternalSideEffectBlockedError(RuntimeError):
    """Raised when shadow code attempts unauthorized real network, subprocess, or external side effects."""
    pass


class ExternalSideEffectGuard:
    """
    Hardened guard against unauthorized external side effects in shadow execution:
    1. Socket calls (non-loopback network) -> BLOCKED
    2. Subprocesses (subprocess.Popen, os.system, os.popen) -> BLOCKED
    3. HTTP / HTTPS client connections -> BLOCKED
    Fails closed immediately.
    """

    def __init__(self, allowed_hosts: Optional[List[str]] = None):
        self.allowed_hosts = set(allowed_hosts or ["127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"])
        self._orig_socket_connect = socket.socket.connect
        self._orig_popen = subprocess.Popen
        self._orig_os_system = os.system
        self._orig_os_popen = os.popen
        self._orig_http_connect = http.client.HTTPConnection.connect
        self._orig_https_connect = http.client.HTTPSConnection.connect

    def __enter__(self):
        # 1. Socket guard
        def _guarded_socket_connect(sock_self, address):
            host = address[0] if isinstance(address, tuple) else address
            if host not in self.allowed_hosts:
                raise ExternalSideEffectBlockedError(
                    f"Blocked external network call to host '{host}'. Shadow mode strictly forbids external socket connections."
                )
            return self._orig_socket_connect(sock_self, address)

        # 2. Subprocess guard
        def _guarded_popen(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args")
            raise ExternalSideEffectBlockedError(
                f"Blocked subprocess execution attempt: {cmd}. Shadow mode strictly forbids spawning subprocesses."
            )

        def _guarded_os_system(cmd):
            raise ExternalSideEffectBlockedError(
                f"Blocked os.system execution attempt: {cmd}. Shadow mode strictly forbids shell commands."
            )

        def _guarded_os_popen(cmd, *args, **kwargs):
            raise ExternalSideEffectBlockedError(
                f"Blocked os.popen execution attempt: {cmd}. Shadow mode strictly forbids shell commands."
            )

        # 3. HTTP guard
        def _guarded_http_connect(conn_self):
            if conn_self.host not in self.allowed_hosts:
                raise ExternalSideEffectBlockedError(
                    f"Blocked HTTP connection to '{conn_self.host}:{conn_self.port}'. Shadow mode strictly forbids external HTTP."
                )
            return self._orig_http_connect(conn_self)

        def _guarded_https_connect(conn_self):
            if conn_self.host not in self.allowed_hosts:
                raise ExternalSideEffectBlockedError(
                    f"Blocked HTTPS connection to '{conn_self.host}:{conn_self.port}'. Shadow mode strictly forbids external HTTPS."
                )
            return self._orig_https_connect(conn_self)

        self._patch_socket = patch.object(socket.socket, "connect", _guarded_socket_connect)
        self._patch_popen = patch.object(subprocess, "Popen", _guarded_popen)
        self._patch_os_system = patch.object(os, "system", _guarded_os_system)
        self._patch_os_popen = patch.object(os, "popen", _guarded_os_popen)
        self._patch_http = patch.object(http.client.HTTPConnection, "connect", _guarded_http_connect)
        self._patch_https = patch.object(http.client.HTTPSConnection, "connect", _guarded_https_connect)

        self._patch_socket.start()
        self._patch_popen.start()
        self._patch_os_system.start()
        self._patch_os_popen.start()
        self._patch_http.start()
        self._patch_https.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._patch_https.stop()
        self._patch_http.stop()
        self._patch_os_popen.stop()
        self._patch_os_system.stop()
        self._patch_popen.stop()
        self._patch_socket.stop()


@contextmanager
def scoped_workspace_store(isolated_store: SyntheticWorkspaceStore):
    """
    Context manager activating an isolated SyntheticWorkspaceStore using Python ContextVar.
    Thread and async-coroutine safe: concurrent tasks will never see each other's workspace.
    """
    token = _current_workspace_store.set(isolated_store)
    try:
        yield isolated_store
    finally:
        _current_workspace_store.reset(token)


def compute_workspace_fingerprint(store: SyntheticWorkspaceStore) -> str:
    """
    Computes a deterministic SHA-256 fingerprint of the synthetic workspace state.
    Includes count of artifacts, email IDs, project milestone statuses, and escalations.
    """
    escalations = getattr(store, "escalations", [])
    summary = {
        "email_count": len(store.emails),
        "email_ids": sorted([e["id"] for e in store.emails]),
        "contract_count": len(store.contracts),
        "contract_ids": sorted([c["id"] for c in store.contracts]),
        "project_count": len(store.projects),
        "project_milestones": {
            p["id"]: [(m.get("id"), m.get("status")) for m in p.get("milestones", [])]
            for p in sorted(store.projects, key=lambda x: x["id"])
        },
        "invoice_count": len(store.invoices),
        "calendar_count": len(store.calendar),
        "escalation_count": len(escalations),
        "escalation_ids": sorted([e["id"] for e in escalations]),
    }
    encoded = json.dumps(summary, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def clone_workspace_store(source: SyntheticWorkspaceStore) -> SyntheticWorkspaceStore:
    """
    Creates an independent deep-copy clone of a SyntheticWorkspaceStore.
    Mutations on the clone have zero effect on the original or sibling clones.
    """
    cloned = SyntheticWorkspaceStore()
    cloned.emails = copy.deepcopy(source.emails)
    cloned.contracts = copy.deepcopy(source.contracts)
    cloned.projects = copy.deepcopy(source.projects)
    cloned.invoices = copy.deepcopy(source.invoices)
    cloned.calendar = copy.deepcopy(source.calendar)
    cloned.escalations = copy.deepcopy(getattr(source, "escalations", []))
    return cloned


def diff_workspace_states(
    initial: SyntheticWorkspaceStore,
    final: SyntheticWorkspaceStore,
) -> Dict[str, Any]:
    """Extracts meaningful mutations produced in a synthetic workspace during a run."""
    init_email_ids = set(e["id"] for e in initial.emails)
    new_emails = [e for e in final.emails if e["id"] not in init_email_ids]

    init_esc_ids = set(e["id"] for e in getattr(initial, "escalations", []))
    new_escs = [e for e in getattr(final, "escalations", []) if e["id"] not in init_esc_ids]

    init_milestones = {
        (p["id"], m["id"]): m.get("status")
        for p in initial.projects
        for m in p.get("milestones", [])
    }
    modified_milestones = []
    for p in final.projects:
        for m in p.get("milestones", []):
            prev_status = init_milestones.get((p["id"], m["id"]))
            if prev_status != m.get("status"):
                modified_milestones.append({
                    "project": p["id"],
                    "milestone": m["id"],
                    "old_status": prev_status,
                    "new_status": m.get("status"),
                })

    return {
        "new_emails_count": len(new_emails),
        "new_emails": [{"id": e["id"], "subject": e["subject"], "to": e["to"]} for e in new_emails],
        "new_escalations_count": len(new_escs),
        "new_escalations": [{"id": e["id"], "title": e["title"]} for e in new_escs],
        "modified_milestones": modified_milestones,
    }

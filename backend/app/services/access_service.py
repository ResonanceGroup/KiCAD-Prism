import json
import os
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.roles import Role, normalize_role

ROLE_STORE_VERSION = "1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("Invalid email")
    return normalized


def _bootstrap_admin_set() -> set[str]:
    return {email.strip().lower() for email in settings.BOOTSTRAP_ADMIN_USERS if email.strip()}


def _default_store() -> dict[str, Any]:
    return {
        "version": ROLE_STORE_VERSION,
        "updated_at": _now_iso(),
        "updated_by": "system",
        "users": {},
    }


def _role_store_path() -> str:
    return settings.RESOLVED_ROLE_STORE_PATH


def _ensure_role_store_directory() -> None:
    os.makedirs(os.path.dirname(_role_store_path()), exist_ok=True)


def _load_role_store() -> dict[str, Any]:
    path = _role_store_path()
    if not os.path.exists(path):
        return _default_store()

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return _default_store()
        users = payload.get("users")
        if not isinstance(users, dict):
            payload["users"] = {}
        return payload
    except (OSError, json.JSONDecodeError):
        return _default_store()


def _save_role_store(payload: dict[str, Any]) -> None:
    _ensure_role_store_directory()
    path = _role_store_path()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def _entry_to_role(entry: Any) -> Role | None:
    if isinstance(entry, str):
        return normalize_role(entry)
    if isinstance(entry, dict):
        return normalize_role(entry.get("role"))
    return None


def resolve_user_role(email: str) -> Role | None:
    normalized_email = _normalize_email(email)
    if normalized_email in _bootstrap_admin_set():
        return "admin"

    payload = _load_role_store()
    users = payload.get("users") or {}
    return _entry_to_role(users.get(normalized_email))


def list_role_assignments() -> list[dict[str, str]]:
    payload = _load_role_store()
    users = payload.get("users") or {}
    bootstrap_admins = _bootstrap_admin_set()

    assignments: list[dict[str, str]] = []
    for email, value in users.items():
        if email in bootstrap_admins:
            assignments.append({"email": str(email), "role": "admin", "source": "bootstrap"})
            continue
        role = _entry_to_role(value)
        if not role:
            continue
        assignments.append({"email": str(email), "role": role, "source": "store"})

    bootstrap_only = bootstrap_admins - {entry["email"] for entry in assignments}
    for email in sorted(bootstrap_only):
        assignments.append({"email": email, "role": "admin", "source": "bootstrap"})

    assignments.sort(key=lambda item: item["email"])
    return assignments


def upsert_user_role(email: str, role: Role, updated_by: str) -> dict[str, str]:
    normalized_email = _normalize_email(email)
    if normalized_email in _bootstrap_admin_set():
        if role != "admin":
            raise ValueError("Cannot override bootstrap admin role assignment")
        return {"email": normalized_email, "role": "admin", "source": "bootstrap"}

    payload = _load_role_store()
    users = payload.setdefault("users", {})
    users[normalized_email] = {
        "role": role,
        "updated_at": _now_iso(),
        "updated_by": _normalize_email(updated_by),
    }
    payload["version"] = ROLE_STORE_VERSION
    payload["updated_at"] = _now_iso()
    payload["updated_by"] = _normalize_email(updated_by)
    _save_role_store(payload)

    return {"email": normalized_email, "role": role, "source": "store"}


def delete_user_role(email: str, updated_by: str) -> bool:
    normalized_email = _normalize_email(email)
    if normalized_email in _bootstrap_admin_set():
        raise ValueError("Cannot delete bootstrap admin role assignment")

    payload = _load_role_store()
    users = payload.setdefault("users", {})
    if normalized_email not in users:
        return False

    users.pop(normalized_email, None)
    payload["updated_at"] = _now_iso()
    payload["updated_by"] = _normalize_email(updated_by)
    _save_role_store(payload)
    return True


# ---------------------------------------------------------------------------
# Pending-approvals queue
# ---------------------------------------------------------------------------

def add_pending_user(email: str) -> None:
    """Add an email to the pending-approvals queue if not already present."""
    normalized = _normalize_email(email)
    payload = _load_role_store()
    pending = payload.setdefault("pending", {})
    if normalized not in pending:
        pending[normalized] = {"registered_at": _now_iso()}
        payload["updated_at"] = _now_iso()
        _save_role_store(payload)


def list_pending_users() -> list[dict[str, str]]:
    """Return all entries in the pending-approvals queue."""
    payload = _load_role_store()
    pending = payload.get("pending") or {}
    return [
        {"email": email, "registered_at": info.get("registered_at", "")}
        for email, info in pending.items()
    ]


def remove_pending_user(email: str) -> None:
    """Remove an email from the pending-approvals queue."""
    normalized = _normalize_email(email)
    payload = _load_role_store()
    pending = payload.setdefault("pending", {})
    if normalized in pending:
        pending.pop(normalized)
        payload["updated_at"] = _now_iso()
        _save_role_store(payload)

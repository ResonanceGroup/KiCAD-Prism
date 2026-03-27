import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
import os
import subprocess
from pathlib import Path
from pydantic import BaseModel
import logging
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.roles import Role, normalize_role
from app.core.security import AuthenticatedUser, require_admin
from app.db.db import get_async_session
from app.db.models import ProjectAccessRequest, ProjectInvite, ProjectMembership, User
from app.services import access_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])

# In Docker, home is /root. SSH keys are usually in ~/.ssh
# We use resolve() to get the absolute path to avoid any ambiguity
SSH_DIR = (Path.home() / ".ssh").resolve()
PRIVATE_KEY = SSH_DIR / "id_ed25519"
PUBLIC_KEY = SSH_DIR / "id_ed25519.pub"

class SSHKeyResponse(BaseModel):
    exists: bool
    public_key: str | None = None

class GenerateSSHKeyRequest(BaseModel):
    email: str = "kicad-prism@example.com"


class RoleAssignmentResponse(BaseModel):
    email: str
    role: Role
    source: str


class UpsertRoleRequest(BaseModel):
    role: str

@router.get("/ssh-key", response_model=SSHKeyResponse)
async def get_ssh_key():
    """Get the current SSH public key if it exists."""
    logger.info(f"Checking for SSH public key at: {PUBLIC_KEY}")
    if not PUBLIC_KEY.exists():
        logger.info("SSH public key not found.")
        return {"exists": False, "public_key": None}
    
    try:
        with open(PUBLIC_KEY, "r") as f:
            key_content = f.read().strip()
            logger.info("SSH public key found and read successfully.")
            return {"exists": True, "public_key": key_content}
    except Exception as e:
        logger.error(f"Error reading public key: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading public key: {str(e)}")

@router.post("/ssh-key/generate")
async def generate_ssh_key(request: GenerateSSHKeyRequest):
    """Generate a new Ed25519 SSH key."""
    logger.info(f"Starting SSH key generation for email: {request.email}")
    logger.info(f"SSH Directory: {SSH_DIR}")
    logger.info(f"Private Key Path: {PRIVATE_KEY}")
    logger.info(f"Public Key Path: {PUBLIC_KEY}")

    if PRIVATE_KEY.exists():
        logger.info("Existing private key found. Removing it.")
        try:
             os.remove(PRIVATE_KEY)
             if PUBLIC_KEY.exists():
                 os.remove(PUBLIC_KEY)
                 logger.info("Existing public key removed.")
        except OSError as e:
             logger.error(f"Failed to remove existing key: {e}")
             raise HTTPException(status_code=500, detail=f"Failed to remove existing key: {e}")
    
    # Ensure .ssh directory exists and has correct permissions
    try:
        if not SSH_DIR.exists():
            logger.info(f"Creating SSH directory: {SSH_DIR}")
            SSH_DIR.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Setting permissions 0o700 on {SSH_DIR}")
        os.chmod(SSH_DIR, 0o700)
    except Exception as e:
        logger.error(f"Failed to create/chmod SSH directory: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to setup SSH directory: {str(e)}")
    
    try:
        # Generate key without passphrase (-N "")
        command = ["ssh-keygen", "-t", "ed25519", "-C", request.email, "-N", "", "-f", str(PRIVATE_KEY)]
        logger.info(f"Running command: {' '.join(command)}")
        
        subprocess.run(
            command,
            check=True,
            capture_output=True
        )
        logger.info("ssh-keygen command completed successfully.")
        
        # Ensure private key has correct permissions
        if PRIVATE_KEY.exists():
            logger.info(f"Setting permissions 0o600 on {PRIVATE_KEY}")
            os.chmod(PRIVATE_KEY, 0o600)
        else:
            logger.error("Private key file not found after generation!")
            raise HTTPException(status_code=500, detail="Key generation appeared to succeed but file is missing.")
        
        with open(PUBLIC_KEY, "r") as f:
            content = f.read().strip()
            logger.info("Public key read successfully returning result.")
            return {"success": True, "public_key": content}

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown error"
        logger.error(f"ssh-keygen failed: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Failed to generate SSH key: {error_msg}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during key generation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@router.get("/access/users", response_model=List[RoleAssignmentResponse])
async def list_access_users():
    return [RoleAssignmentResponse(**item) for item in access_service.list_role_assignments()]


@router.put("/access/users/{email}", response_model=RoleAssignmentResponse)
async def upsert_access_user(
    email: str,
    request: UpsertRoleRequest,
    user: AuthenticatedUser = Depends(require_admin),
):
    normalized_role = normalize_role(request.role)
    if normalized_role is None:
        raise HTTPException(status_code=400, detail="Invalid role. Must be admin, designer, or viewer.")

    try:
        assignment = access_service.upsert_user_role(email=email, role=normalized_role, updated_by=user.email)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    return RoleAssignmentResponse(**assignment)


@router.delete("/access/users/{email}")
async def delete_access_user(email: str, user: AuthenticatedUser = Depends(require_admin)):
    try:
        deleted = access_service.delete_user_role(email=email, updated_by=user.email)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    if not deleted:
        raise HTTPException(status_code=404, detail="User role assignment not found")

    return {"deleted": email.strip().lower()}


# ---------------------------------------------------------------------------
# Pending-approvals endpoints
# ---------------------------------------------------------------------------

class PendingUserResponse(BaseModel):
    email: str
    registered_at: str


@router.get("/pending-users", response_model=List[PendingUserResponse])
async def list_pending_users(session: AsyncSession = Depends(get_async_session)):
    """List all users awaiting admin approval.

    Merges the explicit pending queue with any DB accounts that have no RBAC
    role assigned (e.g. users who registered before the queue was introduced).
    Bootstrap admins are always excluded.
    """
    from app.core.config import settings as app_settings

    # Start with the explicit pending queue (has registered_at timestamps).
    queued = {item["email"]: item for item in access_service.list_pending_users()}

    # Also find DB users with no role who aren't bootstrap admins.
    result = await session.execute(select(User))
    db_users = result.unique().scalars().all()
    bootstrap = {e.strip().lower() for e in app_settings.BOOTSTRAP_ADMIN_USERS if e.strip()}
    for db_user in db_users:
        email = db_user.email.strip().lower()
        if email in bootstrap:
            continue
        if access_service.resolve_user_role(email) is not None:
            continue
        if email not in queued:
            # Back-fill into the queue so approve/deny work normally.
            try:
                access_service.add_pending_user(email)
            except Exception:
                pass
            queued[email] = {"email": email, "registered_at": ""}

    return [PendingUserResponse(**item) for item in queued.values()]


@router.post("/pending-users/{email}/approve")
async def approve_pending_user(
    email: str,
    user: AuthenticatedUser = Depends(require_admin),
):
    """Approve a pending registration: assign viewer role and notify the user."""
    normalized = email.strip().lower()
    try:
        access_service.upsert_user_role(normalized, "viewer", user.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    access_service.remove_pending_user(normalized)
    from app.auth import _send_smtp_email
    await _send_smtp_email(
        to=normalized,
        subject="Your KiCAD Prism account has been approved",
        body_html=(
            "<p>Your KiCAD Prism account registration has been approved.</p>"
            "<p>You can now sign in and access the workspace.</p>"
        ),
    )
    return {"approved": normalized}


@router.post("/pending-users/{email}/deny")
async def deny_pending_user(
    email: str,
    user: AuthenticatedUser = Depends(require_admin),
):
    """Deny a pending registration: remove from queue and notify the user."""
    normalized = email.strip().lower()
    access_service.remove_pending_user(normalized)
    from app.auth import _send_smtp_email
    await _send_smtp_email(
        to=normalized,
        subject="Your KiCAD Prism account registration",
        body_html=(
            "<p>Your KiCAD Prism account registration has been reviewed.</p>"
            "<p>Unfortunately, access has been denied at this time.</p>"
            "<p>Please contact your administrator for more information.</p>"
        ),
    )
    return {"denied": normalized}


# ---------------------------------------------------------------------------
# Registered users list
# ---------------------------------------------------------------------------

class UserListResponse(BaseModel):
    email: str
    is_active: bool
    is_verified: bool
    role: Optional[str] = None


@router.get("/users", response_model=List[UserListResponse])
async def list_all_users(session: AsyncSession = Depends(get_async_session)):
    """List all registered user accounts."""
    result = await session.execute(select(User))
    users = result.unique().scalars().all()
    assignments = {a["email"].lower(): a["role"] for a in access_service.list_role_assignments()}
    return [
        UserListResponse(
            email=u.email,
            is_active=u.is_active,
            is_verified=u.is_verified,
            role=assignments.get(u.email.lower()),
        )
        for u in users
    ]


@router.delete("/users/{email}")
async def delete_user(
    email: str,
    caller: AuthenticatedUser = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
):
    """Permanently delete a user account and all associated data.

    Deletion is blocked when the target user is the sole explicit admin of
    any project.  The caller must first assign another admin to those
    projects before retrying.
    """
    normalized = email.strip().lower()
    if normalized == caller.email.strip().lower():
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    result = await session.execute(select(User).where(User.email == normalized))
    user = result.unique().scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # ------------------------------------------------------------------
    # Guard: block if user is the sole explicit admin of any project.
    # Only consider projects that still exist in the registry — orphaned
    # membership rows for deleted projects are cleaned up, not blocking.
    # ------------------------------------------------------------------
    from app.services import project_service

    admin_project_rows = await session.execute(
        select(ProjectMembership.project_id).where(
            ProjectMembership.user_email == normalized,
            ProjectMembership.project_role == "admin",
        )
    )
    admin_project_ids = [row[0] for row in admin_project_rows.all()]

    # Filter out projects that no longer exist in the registry
    active_admin_project_ids = [
        pid for pid in admin_project_ids
        if project_service.get_project_by_id(pid) is not None
    ]

    # Clean up orphaned membership rows for deleted projects
    orphaned_project_ids = set(admin_project_ids) - set(active_admin_project_ids)
    if orphaned_project_ids:
        for orphaned_id in orphaned_project_ids:
            await session.execute(
                delete(ProjectMembership).where(
                    ProjectMembership.project_id == orphaned_id,
                )
            )
        logger.info(
            "Cleaned up orphaned membership rows for deleted projects: %s",
            orphaned_project_ids,
        )

    sole_admin_projects: list[str] = []
    for project_id in active_admin_project_ids:
        other_admin_count = await session.scalar(
            select(func.count(ProjectMembership.id)).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.project_role == "admin",
                ProjectMembership.user_email != normalized,
            )
        )
        if (other_admin_count or 0) == 0:
            sole_admin_projects.append(project_id)

    if sole_admin_projects:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "User is the sole admin of one or more projects. "
                    "Assign another admin to each project before deleting this user."
                ),
                "sole_admin_projects": sole_admin_projects,
            },
        )

    # ------------------------------------------------------------------
    # Remove RBAC role assignment (ignore if not present or already gone).
    # ------------------------------------------------------------------
    try:
        access_service.delete_user_role(normalized, caller.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error removing role for %s: %s", normalized, exc)
        raise

    # ------------------------------------------------------------------
    # Remove from pending-approvals queue (no-op if not there).
    # ------------------------------------------------------------------
    try:
        access_service.remove_pending_user(normalized)
    except Exception as exc:
        logger.warning("Could not remove pending user entry for %s: %s", normalized, exc)

    # ------------------------------------------------------------------
    # Delete per-project rows that reference this user's email.
    # ------------------------------------------------------------------
    await session.execute(
        delete(ProjectMembership).where(ProjectMembership.user_email == normalized)
    )
    await session.execute(
        delete(ProjectAccessRequest).where(ProjectAccessRequest.user_email == normalized)
    )
    await session.execute(
        delete(ProjectInvite).where(ProjectInvite.invited_email == normalized)
    )

    # Delete the user; cascade="all, delete-orphan" on User.oauth_accounts
    # ensures OAuthAccount rows are removed automatically.
    await session.delete(user)
    await session.commit()
    return {"deleted": normalized}


@router.post("/users/{email}/resend-verification")
async def resend_verification_email(
    email: str,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Re-send the email verification link for an unverified user account."""
    from fastapi_users.db import SQLAlchemyUserDatabase
    from app.db.models import OAuthAccount
    from app.auth import UserManager

    normalized = email.strip().lower()
    result = await session.execute(select(User).where(User.email == normalized))
    user = result.unique().scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="User is already verified")

    user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
    manager = UserManager(user_db)
    try:
        await manager.request_verify(user, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send verification email: {exc}")
    return {"sent": normalized}


# ---------------------------------------------------------------------------
# SMTP test
# ---------------------------------------------------------------------------

@router.post("/smtp/test")
async def test_smtp(user: AuthenticatedUser = Depends(require_admin)):
    """Send a test email to the requesting admin to verify SMTP configuration."""
    if not settings.SMTP_HOST:
        raise HTTPException(status_code=400, detail="SMTP is not configured (SMTP_HOST is empty)")
    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "KiCAD Prism — SMTP Test"
    msg["From"] = from_addr
    msg["To"] = user.email
    msg.attach(MIMEText(
        "<p>This is a test email from <strong>KiCAD Prism</strong>.</p>"
        "<p>If you received this, your SMTP configuration is working correctly.</p>",
        "html",
    ))
    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                if settings.SMTP_USER and settings.SMTP_PASS:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASS)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                if settings.SMTP_TLS:
                    smtp.starttls()
                if settings.SMTP_USER and settings.SMTP_PASS:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASS)
                smtp.send_message(msg)
        return {"success": True, "message": f"Test email sent to {user.email}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SMTP error: {exc}")

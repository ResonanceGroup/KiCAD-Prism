import logging
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.comments import router as comments_router
from app.api.diff import router as diff_router
from app.api.folders import router as folders_router
from app.api.github_repos import router as github_repos_router
from app.api.github_webhook import router as github_webhook_router
from app.api.project_acl import router as project_acl_router
from app.api.projects import router as projects_router
from app.api.settings import router as settings_router
from app.api.workspace import router as workspace_router
from app.auth import (
    UserCreate,
    UserRead,
    auth_backend,
    fastapi_users_instance,
    github_oauth_client,
)
from app.core.config import settings
from app.db.db import async_session_maker, engine
from app.db.models import Base
from app.services.comments_store_service import initialize_comments_store

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
SUBPROCESS_TIMEOUT_SECONDS = 8
KNOWN_GIT_HOSTS = ("github.com", "gitlab.com")

def configure_git():
    """Configure Git with GITHUB_TOKEN if available."""
    if settings.GITHUB_TOKEN:
        logger.info("Configuring Git to use GITHUB_TOKEN...")
        try:
            # git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
            token_url = f"https://{settings.GITHUB_TOKEN}@github.com/"
            subprocess.run(
                ["git", "config", "--global", f"url.{token_url}.insteadOf", "https://github.com/"],
                check=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
            logger.info("Git successfully configured with token injection.")
        except (subprocess.SubprocessError, OSError) as error:
            logger.error("Failed to configure Git with token: %s", error)

def scan_known_hosts():
    """Scan and add GitHub/GitLab to known_hosts if missing."""
    ssh_dir = Path.home() / ".ssh"
    known_hosts = ssh_dir / "known_hosts"
    
    # Ensure known_hosts exists
    if not known_hosts.exists():
        try:
            known_hosts.touch(mode=0o644)
        except Exception as e:
            logger.error(f"Failed to create known_hosts file: {e}")
            return

    for host in KNOWN_GIT_HOSTS:
        try:
            # Check if host is already known using ssh-keygen -F (Find)
            # This checks hashed hosts too
            result = subprocess.run(
                ["ssh-keygen", "-F", host],
                capture_output=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
            
            if result.returncode != 0:
                logger.info(f"Host {host} not found in known_hosts. Scanning...")
                # Scan and append to known_hosts
                scan = subprocess.run(
                    ["ssh-keyscan", "-H", host],
                    capture_output=True,
                    text=True,
                    timeout=SUBPROCESS_TIMEOUT_SECONDS,
                )
                if scan.returncode == 0 and scan.stdout:
                    with open(known_hosts, "a", encoding="utf-8") as f:
                        f.write(scan.stdout)
                    logger.info(f"Successfully added {host} to known_hosts.")
                else:
                    logger.warning(f"Failed to scan {host}. Error: {scan.stderr}")
            else:
                logger.debug(f"Host {host} already in known_hosts.")
                
        except (subprocess.SubprocessError, OSError) as error:
            logger.error("Error checking/scanning host %s: %s", host, error)

def ensure_ssh_dir():
    """Ensure ~/.ssh exists and has correct permissions."""
    ssh_dir = Path.home() / ".ssh"
    try:
        ssh_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(ssh_dir, 0o700)
        
        scan_known_hosts()
        
        logger.info("SSH directory configured correctly.")
    except OSError as error:
        logger.error("Failed to configure SSH directory: %s", error)

async def ensure_admin_user() -> None:
    """Auto-create the bootstrap admin account on first startup.

    Only runs when both ADMIN_EMAIL and ADMIN_PASSWORD are set in the environment.
    If the account already exists the function is a no-op, so restarts are safe.
    """
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return

    from sqlalchemy import select
    from fastapi_users.db import SQLAlchemyUserDatabase
    from app.db.models import OAuthAccount, User
    from app.auth import UserCreate, UserManager

    async with async_session_maker() as session:
        user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
        stmt = select(User).where(User.email == settings.ADMIN_EMAIL.strip().lower())
        result = await session.execute(stmt)
        if result.unique().scalar_one_or_none() is not None:
            logger.debug("Bootstrap admin %s already exists; skipping creation.", settings.ADMIN_EMAIL)
            return

        manager = UserManager(user_db)
        await manager.create(
            UserCreate(
                email=settings.ADMIN_EMAIL.strip().lower(),
                password=settings.ADMIN_PASSWORD,
                is_verified=True,
            ),
            safe=False,
        )
        logger.info("Bootstrap admin account created: %s", settings.ADMIN_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_git()
    ensure_ssh_dir()
    initialize_comments_store()
    await ensure_admin_user()
    yield


app = FastAPI(title="KiCAD Prism API", lifespan=lifespan)

# Configure CORS
# ---------------------------------------------------------------------------
# Entry point when run directly: python -m app.main
# Reads BACKEND_HOST / BACKEND_PORT from .env so the bind address is
# controlled by configuration rather than a hardcoded command-line flag.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
    )

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
# NOTE: project_acl_router must come BEFORE projects_router so that its literal
# routes (e.g. GET /discover, POST /create) are matched before the parameterised
# GET /{project_id} wildcard in projects_router swallows them.
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(github_repos_router, prefix="/api/github", tags=["github"])
app.include_router(github_webhook_router, prefix="/api/github", tags=["github"])
app.include_router(project_acl_router, prefix="/api/projects", tags=["project-acl"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(comments_router, prefix="/api/projects", tags=["comments"])
app.include_router(diff_router, prefix="/api/projects", tags=["diff"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(folders_router, prefix="/api/folders", tags=["folders"])
app.include_router(workspace_router, prefix="/api/workspace", tags=["workspace"])

# ---------------------------------------------------------------------------
# fastapi-users: email/password routers
# ---------------------------------------------------------------------------
app.include_router(
    fastapi_users_instance.get_auth_router(auth_backend),
    prefix="/api/auth/email",
    tags=["auth"],
)
app.include_router(
    fastapi_users_instance.get_register_router(UserRead, UserCreate),
    prefix="/api/auth/email",
    tags=["auth"],
)
app.include_router(
    fastapi_users_instance.get_reset_password_router(),
    prefix="/api/auth/email",
    tags=["auth"],
)
app.include_router(
    fastapi_users_instance.get_verify_router(UserRead),
    prefix="/api/auth/email",
    tags=["auth"],
)

# ---------------------------------------------------------------------------
# fastapi-users: GitHub OAuth router
# ---------------------------------------------------------------------------
app.include_router(
    fastapi_users_instance.get_oauth_router(
        github_oauth_client,
        auth_backend,
        settings.SESSION_SECRET,
        associate_by_email=True,
        is_verified_by_default=True,
    ),
    prefix="/api/auth/github",
    tags=["auth"],
)

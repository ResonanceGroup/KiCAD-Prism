import uuid

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.comments import router as comments_router
from app.api.diff import router as diff_router
from app.api.folders import router as folders_router
from app.api.settings import router as settings_router
from app.api.workspace import router as workspace_router
from app.db.db import engine, get_user_db
from app.db.models import Base, User
from app.services.comments_store_service import initialize_comments_store
from app.core.config import settings
import subprocess
import os
from pathlib import Path
from contextlib import asynccontextmanager

import logging

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_git()
    ensure_ssh_dir()
    initialize_comments_store()
    yield


# ---------------------------------------------------------------------------
# FastAPIUsers – cookie transport backed by SESSION_SECRET (HttpOnly JWT)
# ---------------------------------------------------------------------------

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.SESSION_SECRET
    verification_token_secret = settings.SESSION_SECRET


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)


cookie_transport = CookieTransport(
    cookie_httponly=True,
    cookie_secure=settings.SESSION_COOKIE_SECURE,
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.SESSION_SECRET,
        lifetime_seconds=settings.SESSION_TTL_HOURS * 3600,
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

app = FastAPI(title="KiCAD Prism API", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(comments_router, prefix="/api/projects", tags=["comments"])
app.include_router(diff_router, prefix="/api/projects", tags=["diff"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(folders_router, prefix="/api/folders", tags=["folders"])
app.include_router(workspace_router, prefix="/api/workspace", tags=["workspace"])

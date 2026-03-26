"""
Application configuration with environment variable support.

Configuration can be set via:
1. Environment variables
2. .env file in the backend directory

See .env.example for available configuration options.
"""
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ===========================================
    # Google OAuth Configuration
    # ===========================================
    GOOGLE_CLIENT_ID: str = Field(
        default="",
        description="OAuth Client ID from Google Cloud Console. Leave empty to skip authentication."
    )
    
    # ===========================================
    # Authentication & Access Control
    # ===========================================
    WORKSPACE_NAME: str = Field(
        default="KiCAD Prism",
        description="Display name shown to users when signing into this workspace."
    )

    # Explicitly enable/disable authentication. 
    # If not set, it's auto-determined by GOOGLE_CLIENT_ID and DEV_MODE.
    AUTH_ENABLED_OVERRIDE: bool = Field(
        default=True,
        alias="AUTH_ENABLED",
        description="Explicitly enable/disable authentication."
    )
    
    # Comma-separated list of allowed user emails
    ALLOWED_USERS_STR: str = Field(
        default="",
        description="Comma-separated list of allowed user emails"
    )

    # Comma-separated list of allowed email domains (legacy compatibility).
    ALLOWED_DOMAINS_STR: str = Field(
        default="",
        description="Comma-separated list of allowed email domains"
    )

    # Primary admin email - always has admin access and receives system notifications.
    ADMIN_EMAIL: str = Field(
        default="",
        description="Primary admin email address. Always grants admin role and receives system notifications."
    )

    # Password for the auto-created admin account. Only used on first startup to seed
    # the account; changing this value later has no effect on an existing account.
    ADMIN_PASSWORD: str = Field(
        default="",
        description="Password for the bootstrap admin account. Used only on initial account creation."
    )

    # Comma-separated list of additional bootstrap admin user emails.
    BOOTSTRAP_ADMIN_USERS_STR: str = Field(
        default="",
        description="Comma-separated list of additional admin user emails provisioned from env"
    )

    # Path to persistent role assignment JSON file.
    ROLE_STORE_PATH: str = Field(
        default="",
        description="Path to persistent RBAC role store JSON"
    )

    # Session signing secret for HttpOnly cookie authentication.
    SESSION_SECRET: str = Field(
        default="",
        description="HMAC secret used to sign session cookies"
    )

    # Session TTL in hours.
    SESSION_TTL_HOURS: int = Field(
        default=12,
        ge=1,
        le=168,
        description="Session expiration (hours)"
    )

    # Cookie secure flag (set true behind HTTPS).
    SESSION_COOKIE_SECURE: bool = Field(
        default=False,
        description="Whether session cookie should be marked Secure"
    )
    
    # ===========================================
    # Development Settings
    # ===========================================
    DEV_MODE: bool = Field(
        default=True,
        description="Enable development mode. When True and GOOGLE_CLIENT_ID is empty, bypasses authentication."
    )
    
    # ===========================================
    # GitHub Organization-owned OAuth App (recommended)
    # ===========================================
    GITHUB_CLIENT_ID: str = Field(
        default="",
        description="GitHub OAuth App Client ID."
    )

    GITHUB_CLIENT_SECRET: str = Field(
        default="",
        description="GitHub OAuth App Client Secret."
    )

    # Must match the organization that owns the OAuth App.
    # Leave empty to allow any authenticated GitHub user.
    GITHUB_ORG_LOGIN: str = Field(
        default="",
        description="GitHub organization slug; must match the org that owns the OAuth App (e.g. 'yourcompanyorg')."
    )

    # OAuth scopes requested from GitHub.
    GITHUB_SCOPES: str = Field(
        default="repo,read:org",
        description="Comma-separated GitHub OAuth scopes (e.g. 'repo,read:org')."
    )

    # ===========================================
    # Email / SMTP (for verification + password reset)
    # ===========================================
    SMTP_HOST: str = Field(
        default="",
        description="SMTP server hostname (e.g. smtp.yourmailserver.com)."
    )

    SMTP_PORT: int = Field(
        default=587,
        description="SMTP server port (typically 587 for STARTTLS, 465 for SSL)."
    )

    SMTP_USER: str = Field(
        default="",
        description="SMTP authentication username."
    )

    SMTP_PASS: str = Field(
        default="",
        description="SMTP authentication password."
    )

    SMTP_FROM: str = Field(
        default="",
        description="From address used for outgoing emails (e.g. prism@yourcompany.com)."
    )

    # Set to True to use STARTTLS when connecting to the SMTP server.
    SMTP_TLS: bool = Field(
        default=True,
        description="Enable STARTTLS for the SMTP connection."
    )

    # ===========================================
    # Email domain whitelist for auto-approval
    # ===========================================
    # Comma-separated list of email domains that are automatically approved
    # without requiring an explicit role assignment (e.g. 'yourcompany.com,example.com').
    ALLOWED_EMAIL_DOMAINS_STR: str = Field(
        default="",
        description="Comma-separated email domains eligible for auto-approval."
    )

    # ===========================================
    # GitHub App (for server-side repo operations)
    # ===========================================
    # The GitHub App is used for all repo browsing, cloning, and webhook
    # processing.  It operates independently of any user's OAuth session.

    GITHUB_APP_ID: str = Field(
        default="",
        description="Numeric GitHub App ID (shown on the App settings page).",
    )

    GITHUB_APP_PRIVATE_KEY: str = Field(
        default="",
        description=(
            "GitHub App RSA private key.  Three accepted formats:\n"
            "  1. Base64-encoded PEM (recommended):  base64 -w 0 private-key.pem\n"
            "  2. Raw PEM with escaped newlines:      -----BEGIN RSA PRIVATE KEY-----\\n...\n"
            "  3. Absolute path to a .pem file:       /run/secrets/github-app.pem"
        ),
    )

    GITHUB_APP_INSTALLATION_ID: str = Field(
        default="",
        description=(
            "GitHub App installation ID for the target organization. "
            "Find it at /orgs/{org}/installations or the GitHub App's Installations page."
        ),
    )

    GITHUB_WEBHOOK_SECRET: str = Field(
        default="",
        description=(
            "Webhook secret used to verify HMAC-SHA256 signatures on incoming "
            "GitHub App events.  Must match the secret set in the GitHub App's "
            "webhook settings."
        ),
    )

    # ===========================================
    # Git & GitHub Integration
    # ===========================================
    GITHUB_TOKEN: str = Field(
        default="",
        description="GitHub Personal Access Token for private repository access."
    )

    # ===========================================
    # Token Encryption
    # ===========================================
    TOKEN_ENCRYPTION_KEY: str = Field(
        default="",
        description=(
            "Fernet key used to encrypt GitHub access tokens at rest. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ),
    )

    COMMENTS_API_BASE_URL: str = Field(
        default="",
        description=(
            "Default base URL used to generate KiCad comments REST URLs "
            "for project import and visualizer helpers. "
            "If empty, URL helpers derive host from the incoming request."
        ),
    )

    # Public-facing frontend URL used in verification and password-reset emails.
    # Set this to the URL users open in their browser (e.g. https://prism.yourcompany.com).
    # If empty, the backend request's base_url is used as a fallback (works only when
    # the frontend and API are served on the same origin).
    APP_URL: str = Field(
        default="",
        description="Public frontend URL for email deep-links (e.g. https://prism.yourcompany.com)."
    )

    # ===========================================
    # Network / Server Binding
    # ===========================================
    # Host the backend uvicorn server binds to.
    # Use 0.0.0.0 to accept connections from any network interface (LAN/remote access).
    # Use 127.0.0.1 to restrict to localhost only.
    BACKEND_HOST: str = Field(
        default="127.0.0.1",
        description="Host address the uvicorn server binds to (0.0.0.0 = all interfaces)."
    )

    BACKEND_PORT: int = Field(
        default=8000,
        description="Port the uvicorn server listens on."
    )
    
    # ===========================================
    # Computed Properties
    # ===========================================
    @property
    def ALLOWED_USERS(self) -> List[str]:
        """Parse allowed emails from comma-separated string."""
        return [u.strip().lower() for u in self.ALLOWED_USERS_STR.split(",") if u.strip()]

    @property
    def ALLOWED_DOMAINS(self) -> List[str]:
        """Parse allowed domains from comma-separated string."""
        return [d.strip().lower() for d in self.ALLOWED_DOMAINS_STR.split(",") if d.strip()]

    @property
    def BOOTSTRAP_ADMIN_USERS(self) -> List[str]:
        """All hardcoded admin emails: ADMIN_EMAIL plus any in BOOTSTRAP_ADMIN_USERS_STR."""
        admins: list[str] = []
        if self.ADMIN_EMAIL.strip():
            admins.append(self.ADMIN_EMAIL.strip().lower())
        admins.extend(u.strip().lower() for u in self.BOOTSTRAP_ADMIN_USERS_STR.split(",") if u.strip())
        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for email in admins:
            if email not in seen:
                seen.add(email)
                result.append(email)
        return result

    @property
    def ALLOWED_EMAIL_DOMAINS(self) -> List[str]:
        """Parse auto-approval email domains from comma-separated string."""
        return [d.strip().lower() for d in self.ALLOWED_EMAIL_DOMAINS_STR.split(",") if d.strip()]

    @property
    def KICAD_PROJECTS_ROOT(self) -> str:
        return os.environ.get(
            "KICAD_PROJECTS_ROOT",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/projects")),
        )

    @property
    def RESOLVED_ROLE_STORE_PATH(self) -> str:
        if self.ROLE_STORE_PATH.strip():
            return os.path.abspath(os.path.expanduser(self.ROLE_STORE_PATH.strip()))
        return os.path.join(self.KICAD_PROJECTS_ROOT, ".rbac_roles.json")
    
    @property
    def AUTH_ENABLED(self) -> bool:
        """
        Authentication is enabled when:
        1. AUTH_ENABLED env var is True (default), AND
        2. DEV_MODE is False, AND
        3. At least one auth provider is configured:
           - GOOGLE_CLIENT_ID  (Google OAuth)
           - GITHUB_CLIENT_ID  (GitHub OAuth)
           - SESSION_SECRET    (email/password via fastapi-users)
        """
        if not self.AUTH_ENABLED_OVERRIDE:
            return False
        if self.DEV_MODE:
            return False
        return bool(self.GOOGLE_CLIENT_ID) or bool(self.GITHUB_CLIENT_ID) or bool(self.SESSION_SECRET)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow extra fields to be ignored
        extra = "ignore"


# Global settings instance
settings = Settings()

export type UserRole = "admin" | "designer" | "viewer";

export interface User {
    name: string;
    email: string;
    picture?: string;
    role: UserRole;
    github_connected?: boolean;
    username?: string | null;
    notification_email?: string | null;
    has_password?: boolean;
    github_username?: string | null;
    github_email?: string | null;
}

export interface AuthConfig {
    auth_enabled: boolean;
    dev_mode: boolean;
    google_client_id: string;
    github_client_id: string;
    workspace_name: string;
    providers: string[];
    github_app_configured: boolean;
}

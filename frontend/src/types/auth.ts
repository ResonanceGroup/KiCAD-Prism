export type UserRole = "admin" | "designer" | "viewer";

export interface User {
    name: string;
    email: string;
    picture?: string;
    role: UserRole;
}

export interface AuthConfig {
    auth_enabled: boolean;
    dev_mode: boolean;
    google_client_id: string;
    github_client_id: string;
    workspace_name: string;
    providers: string[];
}

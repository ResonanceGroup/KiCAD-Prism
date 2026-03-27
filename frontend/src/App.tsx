import { Suspense, lazy, useDeferredValue, useEffect, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import type { User, AuthConfig } from './types/auth';
import { Button } from '@/components/ui/button';
import { Toaster, toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Search, Bell, Github, LogOut, CheckCircle2, AlertCircle, Settings, AtSign } from 'lucide-react';
import { ApiHttpError, fetchApi, fetchJson } from '@/lib/api';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import prismLogoMark from './assets/branding/kicad-prism/kicad-prism-icon.svg';

const LoginPage = lazy(() =>
    import('./components/login-page').then((module) => ({ default: module.LoginPage }))
);
const Workspace = lazy(() =>
    import('./components/workspace').then((module) => ({ default: module.Workspace }))
);
const ProjectDetailPage = lazy(() =>
    import('./pages/ProjectDetailPage').then((module) => ({ default: module.ProjectDetailPage }))
);
const ResetPasswordPage = lazy(() =>
    import('./pages/ResetPasswordPage').then((module) => ({ default: module.ResetPasswordPage }))
);
const VerifyEmailPage = lazy(() =>
    import('./pages/VerifyEmailPage').then((module) => ({ default: module.VerifyEmailPage }))
);
const InviteAcceptPage = lazy(() =>
    import('./pages/InviteAcceptPage').then((module) => ({ default: module.InviteAcceptPage }))
);
const ProfilePage = lazy(() =>
    import('./pages/ProfilePage').then((module) => ({ default: module.ProfilePage }))
);

function RouteFallback() {
    return (
        <div className="flex items-center justify-center h-full min-h-[16rem] bg-background">
            <div className="text-muted-foreground">Loading...</div>
        </div>
    );
}

interface PendingInvite {
    id: string;
    project_id: string;
    project_name: string;
    invited_role: string;
    invited_by: string;
    created_at: string;
}

interface PendingAccessRequest {
    id: string;
    project_id: string;
    project_name: string;
    user_email: string;
    requested_role: string;
    requested_at: string;
}

function UsernameSetupDialog({
    user,
    onUserUpdate,
}: {
    user: User;
    onUserUpdate: (u: User) => void;
}) {
    const [value, setValue] = useState(
        // Pre-fill with the GitHub username as a suggestion when there's a
        // conflict (github_username is set but username is still null).
        user.github_username ?? ''
    );
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const isConflict = Boolean(user.github_username && !user.username);
    const isOpen = !user.username;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const username = value.trim();
        if (!username) return;
        setSaving(true);
        setError(null);
        try {
            const updated = await fetchJson<User>('/api/auth/profile', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username }),
            });
            onUserUpdate(updated);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Failed to save username';
            setError(msg);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={isOpen}>
            <DialogContent
                className="sm:max-w-md"
                onInteractOutside={(e) => e.preventDefault()}
                onEscapeKeyDown={(e) => e.preventDefault()}
            >
                <DialogHeader>
                    <DialogTitle>Choose a username</DialogTitle>
                    <DialogDescription>
                        {isConflict
                            ? `The GitHub username "@${user.github_username}" is already taken. Please choose a different username for this app.`
                            : 'Set a unique username for your account. It will be used for @mentions.'}
                    </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-1.5">
                        <Label htmlFor="username-setup-input">Username</Label>
                        <div className="relative">
                            <AtSign className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                id="username-setup-input"
                                className="pl-9"
                                placeholder="your-username"
                                value={value}
                                onChange={(e) => { setValue(e.target.value); setError(null); }}
                                minLength={3}
                                maxLength={50}
                                required
                                autoFocus
                            />
                        </div>
                        <p className="text-xs text-muted-foreground">
                            3–50 characters. Letters, numbers, underscores, hyphens, and dots only.
                        </p>
                        {error && <p className="text-xs text-destructive">{error}</p>}
                    </div>
                    <DialogFooter>
                        <Button type="submit" disabled={saving || !value.trim()} className="w-full">
                            {saving ? 'Saving…' : 'Save username'}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

function App() {
    const [user, setUser] = useState<User | null>(null);
    const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [authError, setAuthError] = useState<string | null>(null);
    const [workspaceSearchQuery, setWorkspaceSearchQuery] = useState("");
    const deferredWorkspaceSearchQuery = useDeferredValue(workspaceSearchQuery);
    const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);
    const [pendingAccessRequests, setPendingAccessRequests] = useState<PendingAccessRequest[]>([]);
    const [bellOpen, setBellOpen] = useState(false);
    const [profileOpen, setProfileOpen] = useState(false);
    const inviteIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Fetch auth configuration on mount
    useEffect(() => {
        const controller = new AbortController();

        const fetchAuthConfig = async () => {
            try {
                const config = await fetchJson<AuthConfig>(
                    '/api/auth/config',
                    { signal: controller.signal },
                    'Failed to fetch auth config'
                );
                if (controller.signal.aborted) {
                    return;
                }

                setAuthConfig(config);
                setAuthError(null);

                // If auth is disabled, auto-login as guest
                if (!config.auth_enabled) {
                    const guestUser: User = { name: 'Guest', email: 'guest@local', role: 'viewer' };
                    setUser(guestUser);
                    return;
                }

                try {
                    const currentUser = await fetchJson<User>(
                        '/api/auth/me',
                        { signal: controller.signal },
                        'Failed to fetch current user'
                    );
                    if (controller.signal.aborted) {
                        return;
                    }
                    setUser(currentUser);
                    setAuthError(null);
                } catch (err) {
                    if (controller.signal.aborted) {
                        return;
                    }
                    if (err instanceof ApiHttpError && (err.status === 401 || err.status === 403)) {
                        setUser(null);
                        setAuthError(err.status === 403 ? err.message : null);
                    } else {
                        setUser(null);
                    }
                }
            } catch (err) {
                if (controller.signal.aborted) {
                    return;
                }
                console.error('Failed to fetch auth config:', err);
                // On error, default to no auth (allow access)
                const guestUser: User = { name: 'Guest', email: 'guest@local', role: 'viewer' };
                setUser(guestUser);
            } finally {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            }
        };

        fetchAuthConfig();
        return () => controller.abort();
    }, []);

    // Poll for pending invites and access requests when the user is logged in
    useEffect(() => {
        const fetchNotifications = async () => {
            try {
                const [inviteData, accessReqData] = await Promise.all([
                    fetchJson<PendingInvite[]>('/api/projects/invites/pending', {}, 'Failed to fetch invites'),
                    fetchJson<PendingAccessRequest[]>('/api/projects/access-requests/pending', {}, 'Failed to fetch access requests').catch(() => [] as PendingAccessRequest[]),
                ]);
                setPendingInvites(inviteData);
                setPendingAccessRequests(accessReqData);
            } catch {
                // Silently fail — don't disrupt the UI
            }
        };

        if (user && user.email !== 'guest@local') {
            void fetchNotifications();
            inviteIntervalRef.current = setInterval(() => void fetchNotifications(), 30_000);
        } else {
            setPendingInvites([]);
            setPendingAccessRequests([]);
        }

        return () => {
            if (inviteIntervalRef.current) clearInterval(inviteIntervalRef.current);
        };
    }, [user]);

    const handleInviteAccept = async (invite: PendingInvite) => {
        try {
            await fetchApi(`/api/projects/invites/${invite.id}/accept`, { method: 'POST' });
            setPendingInvites((prev) => prev.filter((i) => i.id !== invite.id));
            toast.success(`Joined "${invite.project_name}" as ${invite.invited_role}`);
        } catch {
            toast.error('Failed to accept invite');
        }
    };

    const handleInviteDecline = async (invite: PendingInvite) => {
        try {
            await fetchApi(`/api/projects/invites/${invite.id}/decline`, { method: 'POST' });
            setPendingInvites((prev) => prev.filter((i) => i.id !== invite.id));
            toast.info('Invite declined');
        } catch {
            toast.error('Failed to decline invite');
        }
    };

    const handleAccessRequestApprove = async (req: PendingAccessRequest) => {
        try {
            await fetchApi(`/api/projects/${req.project_id}/access-requests/${req.id}/approve`, { method: 'POST' });
            setPendingAccessRequests((prev) => prev.filter((r) => r.id !== req.id));
            toast.success(`Approved ${req.user_email} for "${req.project_name}"`);
        } catch {
            toast.error('Failed to approve request');
        }
    };

    const handleAccessRequestDeny = async (req: PendingAccessRequest) => {
        try {
            await fetchApi(`/api/projects/${req.project_id}/access-requests/${req.id}/deny`, { method: 'POST' });
            setPendingAccessRequests((prev) => prev.filter((r) => r.id !== req.id));
            toast.info('Request denied');
        } catch {
            toast.error('Failed to deny request');
        }
    };

    useEffect(() => {
        const handleAuthError = (event: Event) => {
            const customEvent = event as CustomEvent<{ status?: number; url?: string }>;
            const status = customEvent.detail?.status;
            const url = customEvent.detail?.url ?? "";
            if (status === 401) {
                setUser(null);
                return;
            }
            if (status === 403 && url.includes('/api/auth/me')) {
                setUser(null);
            }
        };
        window.addEventListener('kicad-prism-auth-error', handleAuthError);
        return () => window.removeEventListener('kicad-prism-auth-error', handleAuthError);
    }, []);

    const handleLogout = () => {
        void fetchApi('/api/auth/logout', { method: 'POST' }).finally(() => {
            setUser(null);
            setAuthError(null);
        });
    };

    // Show loading state while fetching auth config
    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen bg-background">
                <div className="text-muted-foreground">Loading...</div>
            </div>
        );
    }

    // If auth is enabled and no user, show login page
    if (authConfig?.auth_enabled && !user) {
        // Allow unauthenticated access to password-reset and email-verify pages
        const publicPath = window.location.pathname;
        if (publicPath === '/reset-password') {
            return (
                <BrowserRouter>
                    <Toaster richColors position="top-right" />
                    <Suspense fallback={<RouteFallback />}>
                        <ResetPasswordPage />
                    </Suspense>
                </BrowserRouter>
            );
        }
        if (publicPath === '/verify') {
            return (
                <BrowserRouter>
                    <Toaster richColors position="top-right" />
                    <Suspense fallback={<RouteFallback />}>
                        <VerifyEmailPage />
                    </Suspense>
                </BrowserRouter>
            );
        }
        if (publicPath === '/invite/accept') {
            return (
                <BrowserRouter>
                    <Toaster richColors position="top-right" />
                    <Suspense fallback={<RouteFallback />}>
                        <InviteAcceptPage />
                    </Suspense>
                </BrowserRouter>
            );
        }

        // Fallback when no provider is configured
        if (authConfig.providers.length === 0) {
            return (
                <div className="flex items-center justify-center h-screen bg-background">
                    <div className="text-red-500">Error: No authentication provider configured in backend.</div>
                </div>
            );
        }

        return (
            <Suspense fallback={<RouteFallback />}>
                <LoginPage
                    onLoginSuccess={setUser}
                    googleClientId={authConfig.google_client_id}
                    githubClientId={authConfig.github_client_id}
                    providers={authConfig.providers}
                    devMode={authConfig.dev_mode}
                    workspaceName={authConfig.workspace_name}
                    initialError={authError}
                />
            </Suspense>
        );
    }

    // User is authenticated or auth is disabled - show app
    return (
        <BrowserRouter>
            <Toaster richColors position="top-right" />
            {/* Prompt any authenticated non-guest user to set a username if they don't have one */}
            {user && user.email !== 'guest@local' && !user.username && (
                <UsernameSetupDialog user={user} onUserUpdate={setUser} />
            )}
            <Routes>
                <Route path="/" element={
                    <div className="min-h-screen bg-background text-foreground">
                        <header className="border-b sticky top-0 bg-background/95 backdrop-blur z-10">
                            <div className="grid h-16 grid-cols-[auto_1fr_auto] items-center gap-4 px-3 md:px-4">
                                <div className="flex items-center gap-2 text-primary">
                                    <img src={prismLogoMark} alt="KiCAD Prism Logo" className="h-7 w-7 object-contain" />
                                    <span className="text-xl font-bold tracking-tight text-foreground">KiCAD Prism</span>
                                </div>

                                <div className="flex justify-center">
                                    <div className="relative w-full max-w-2xl">
                                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                        <Input
                                            value={workspaceSearchQuery}
                                            onChange={(event) => setWorkspaceSearchQuery(event.target.value)}
                                            placeholder="Search projects by name, description, and metadata"
                                            className="pl-10"
                                        />
                                    </div>
                                </div>

                                <div className="flex items-center gap-4">
                                    {user && user.email !== 'guest@local' && (
                                        <>
                                            {/* Notifications bell */}
                                            <Popover open={bellOpen} onOpenChange={setBellOpen}>
                                                <PopoverTrigger asChild>
                                                    <Button variant="ghost" size="icon" className="relative">
                                                        <Bell className="h-5 w-5" />
                                                        {(pendingInvites.length + pendingAccessRequests.length) > 0 && (
                                                            <Badge
                                                                variant="destructive"
                                                                className="absolute -right-1 -top-1 h-4 min-w-[1rem] rounded-full px-1 text-[10px] leading-none flex items-center justify-center"
                                                            >
                                                                {pendingInvites.length + pendingAccessRequests.length}
                                                            </Badge>
                                                        )}
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent align="end" className="w-80 p-0">
                                                    <div className="border-b px-4 py-2">
                                                        <p className="text-sm font-semibold">Notifications</p>
                                                    </div>
                                                    {pendingInvites.length === 0 && pendingAccessRequests.length === 0 ? (
                                                        <p className="px-4 py-6 text-center text-sm text-muted-foreground">No pending notifications</p>
                                                    ) : (
                                                        <ul className="divide-y max-h-96 overflow-y-auto">
                                                            {pendingAccessRequests.map((req) => (
                                                                <li key={req.id} className="px-4 py-3 space-y-2">
                                                                    <div>
                                                                        <p className="text-sm font-medium">{req.project_name}</p>
                                                                        <p className="text-xs text-muted-foreground">
                                                                            <span className="font-medium">{req.user_email}</span> requested{' '}
                                                                            <span className="capitalize font-medium">{req.requested_role}</span> access
                                                                        </p>
                                                                    </div>
                                                                    <div className="flex gap-2">
                                                                        <Button
                                                                            size="sm"
                                                                            className="h-7 text-xs flex-1"
                                                                            onClick={() => void handleAccessRequestApprove(req)}
                                                                        >
                                                                            Approve
                                                                        </Button>
                                                                        <Button
                                                                            size="sm"
                                                                            variant="outline"
                                                                            className="h-7 text-xs flex-1"
                                                                            onClick={() => void handleAccessRequestDeny(req)}
                                                                        >
                                                                            Deny
                                                                        </Button>
                                                                    </div>
                                                                </li>
                                                            ))}
                                                            {pendingInvites.map((inv) => (
                                                                <li key={inv.id} className="px-4 py-3 space-y-2">
                                                                    <div>
                                                                        <p className="text-sm font-medium">{inv.project_name}</p>
                                                                        <p className="text-xs text-muted-foreground">
                                                                            Invited as <span className="capitalize font-medium">{inv.invited_role}</span> by {inv.invited_by}
                                                                        </p>
                                                                    </div>
                                                                    <div className="flex gap-2">
                                                                        <Button
                                                                            size="sm"
                                                                            className="h-7 text-xs flex-1"
                                                                            onClick={() => void handleInviteAccept(inv)}
                                                                        >
                                                                            Accept
                                                                        </Button>
                                                                        <Button
                                                                            size="sm"
                                                                            variant="outline"
                                                                            className="h-7 text-xs flex-1"
                                                                            onClick={() => void handleInviteDecline(inv)}
                                                                        >
                                                                            Decline
                                                                        </Button>
                                                                    </div>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    )}
                                                </PopoverContent>
                                            </Popover>

                                            {/* User profile popover */}
                                            <Popover open={profileOpen} onOpenChange={setProfileOpen}>
                                                <PopoverTrigger asChild>
                                                    <Button variant="ghost" size="sm" className="flex items-center gap-1.5 px-2">
                                                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                                                            {user.name.charAt(0).toUpperCase()}
                                                        </div>
                                                        <span className="text-sm hidden sm:inline">{user.name}</span>
                                                    </Button>
                                                </PopoverTrigger>
                                                <PopoverContent align="end" className="w-72 p-0">
                                                    {/* Header */}
                                                    <div className="border-b px-4 py-3">
                                                        <p className="text-sm font-semibold truncate">{user.name}</p>
                                                        <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                                                        <Badge variant="outline" className="mt-1 capitalize text-[10px]">
                                                            {user.role}
                                                        </Badge>
                                                    </div>

                                                    {/* GitHub connection section */}
                                                    {authConfig?.github_client_id && (
                                                        <div className="border-b px-4 py-3 space-y-2">
                                                            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                                                GitHub
                                                            </p>
                                                            {user.github_connected ? (
                                                                <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400">
                                                                    <CheckCircle2 className="h-4 w-4 shrink-0" />
                                                                    <span>GitHub account linked</span>
                                                                </div>
                                                            ) : (
                                                                <div className="space-y-2">
                                                                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                                                        <AlertCircle className="h-4 w-4 shrink-0" />
                                                                        <span>GitHub not connected</span>
                                                                    </div>
                                                                    <Button
                                                                        variant="outline"
                                                                        size="sm"
                                                                        className="w-full"
                                                                        onClick={async () => {
                                                                            setProfileOpen(false);
                                                                            try {
                                                                                const res = await fetch(`/api/auth/github/link/authorize`);
                                                                                const data = await res.json();
                                                                                window.location.href = data.authorization_url;
                                                                            } catch {
                                                                                console.error("Failed to start GitHub connect flow");
                                                                            }
                                                                        }}
                                                                    >
                                                                        <Github className="h-4 w-4 mr-2" />
                                                                        Connect GitHub Account
                                                                    </Button>
                                                                    <p className="text-[11px] text-muted-foreground leading-snug">
                                                                        Connecting grants designer access and enables GitHub repository browsing. Your GitHub account must be a member of the organization.
                                                                    </p>
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}

                                                    {/* Account settings & logout */}
                                                    <div className="px-4 py-2">
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="w-full justify-start text-muted-foreground hover:text-foreground"
                                                            asChild
                                                            onClick={() => setProfileOpen(false)}
                                                        >
                                                            <Link to="/profile">
                                                                <Settings className="h-4 w-4 mr-2" />
                                                                Account Settings
                                                            </Link>
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="w-full justify-start text-muted-foreground hover:text-foreground"
                                                            onClick={() => { setProfileOpen(false); handleLogout(); }}
                                                        >
                                                            <LogOut className="h-4 w-4 mr-2" />
                                                            Sign out
                                                        </Button>
                                                    </div>
                                                </PopoverContent>
                                            </Popover>
                                        </>
                                    )}
                                    {user && user.email === 'guest@local' && (
                                        <span className="text-sm text-muted-foreground">Viewing as Guest</span>
                                    )}
                                </div>
                            </div>
                        </header>

                        <main className="h-[calc(100vh-4rem)]">
                            <Suspense fallback={<RouteFallback />}>
                                <Workspace
                                    searchQuery={deferredWorkspaceSearchQuery}
                                    user={user}
                                />
                            </Suspense>
                        </main>
                    </div>
                } />
                <Route
                    path="/project/:projectId"
                    element={
                        <Suspense fallback={<RouteFallback />}>
                            <ProjectDetailPage user={user} />
                        </Suspense>
                    }
                />
                <Route
                    path="/reset-password"
                    element={
                        <Suspense fallback={<RouteFallback />}>
                            <ResetPasswordPage />
                        </Suspense>
                    }
                />
                <Route
                    path="/verify"
                    element={
                        <Suspense fallback={<RouteFallback />}>
                            <VerifyEmailPage />
                        </Suspense>
                    }
                />
                <Route
                    path="/invite/accept"
                    element={
                        <Suspense fallback={<RouteFallback />}>
                            <InviteAcceptPage />
                        </Suspense>
                    }
                />
                <Route
                    path="/profile"
                    element={
                        user ? (
                            <Suspense fallback={<RouteFallback />}>
                                <ProfilePage
                                    user={user}
                                    onUserUpdate={setUser}
                                    githubClientId={authConfig?.github_client_id}
                                />
                            </Suspense>
                        ) : (
                            <Navigate to="/" replace />
                        )
                    }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;

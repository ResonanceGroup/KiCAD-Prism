import { useDeferredValue, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { User, AuthConfig } from './types/auth';
import { LoginPage } from './components/login-page';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { Button } from '@/components/ui/button';
import { Workspace } from './components/workspace';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { Toaster } from 'sonner';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';
import { ApiHttpError, fetchApi, fetchJson } from '@/lib/api';
import prismLogoMark from './assets/branding/kicad-prism/kicad-prism-icon.svg';



function App() {
    const [user, setUser] = useState<User | null>(null);
    const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [authError, setAuthError] = useState<string | null>(null);
    const [workspaceSearchQuery, setWorkspaceSearchQuery] = useState("");
    const deferredWorkspaceSearchQuery = useDeferredValue(workspaceSearchQuery);

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
        // Fallback for missing client ID in config
        if (!authConfig.google_client_id) {
            return (
                <div className="flex items-center justify-center h-screen bg-background">
                    <div className="text-red-500">Error: Missing Google Client ID in backend configuration.</div>
                </div>
            );
        }

        return (
            <GoogleOAuthProvider clientId={authConfig.google_client_id}>
                <LoginPage
                    onLoginSuccess={setUser}
                    devMode={authConfig.dev_mode}
                    workspaceName={authConfig.workspace_name}
                    initialError={authError}
                />
            </GoogleOAuthProvider>
        );
    }

    // User is authenticated or auth is disabled - show app
    return (
        <BrowserRouter>
            <Toaster richColors position="top-right" />
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
                                            <span className="text-sm text-muted-foreground">
                                                Welcome, {user.name} ({user.role})
                                            </span>
                                            <Button variant="ghost" size="sm" onClick={handleLogout}>Logout</Button>
                                        </>
                                    )}
                                    {user && user.email === 'guest@local' && (
                                        <span className="text-sm text-muted-foreground">Viewing as Guest</span>
                                    )}
                                </div>
                            </div>
                        </header>

                        <main className="h-[calc(100vh-4rem)]">
                            <Workspace
                                searchQuery={deferredWorkspaceSearchQuery}
                                user={user}
                            />
                        </main>
                    </div>
                } />
                <Route path="/project/:projectId" element={<ProjectDetailPage user={user} />} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;

import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Github, CheckCircle2, AlertCircle, ArrowLeft, User as UserIcon, Mail, Lock, AtSign, RefreshCw, XCircle } from 'lucide-react';
import { fetchJson, fetchApi, readApiError } from '@/lib/api';
import type { User } from '../types/auth';

interface ProfilePageProps {
    user: User;
    onUserUpdate: (user: User) => void;
    githubClientId?: string;
}

export function ProfilePage({ user, onUserUpdate, githubClientId }: ProfilePageProps) {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();

    // Handle GitHub linking success/failure and refresh user data.
    useEffect(() => {
        const linkError = searchParams.get('link_error');
        const githubLinked = searchParams.get('github_linked');
        
        if (linkError) {
            toast.error('Failed to link GitHub account. Please try again.');
            setSearchParams({}, { replace: true });
        } else if (githubLinked === 'success') {
            // OAuth callback succeeded - refresh user data
            toast.success('GitHub account linked successfully');
            setSearchParams({}, { replace: true });
            fetchJson<User>('/api/auth/me')
                .then(updated => onUserUpdate(updated))
                .catch(() => toast.error('Failed to refresh user data'));
        }
    }, [searchParams, setSearchParams, onUserUpdate]);

    // Username / display name
    const [username, setUsername] = useState(user.username ?? '');
    const [displayName, setDisplayName] = useState(user.name ?? '');
    const [profileSaving, setProfileSaving] = useState(false);

    // Notification email
    const [notifEmail, setNotifEmail] = useState(user.notification_email ?? '');
    const [notifEmailSaving, setNotifEmailSaving] = useState(false);

    // Set password (GitHub-only accounts)
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [passwordSaving, setPasswordSaving] = useState(false);

    // Reset password (email link for accounts that already have a password)
    const [resetLinkSending, setResetLinkSending] = useState(false);

    // Keep form in sync if the parent refreshes the user object
    useEffect(() => {
        setUsername(user.username ?? '');
        setDisplayName(user.name ?? '');
        setNotifEmail(user.notification_email ?? '');
    }, [user]);

    const handleSaveProfile = async (e: React.FormEvent) => {
        e.preventDefault();
        setProfileSaving(true);
        try {
            const updated = await fetchJson<User>('/api/auth/profile', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: username.trim() || null,
                    display_name: displayName.trim() || null,
                }),
            });
            onUserUpdate(updated);
            toast.success('Profile updated');
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Failed to save profile';
            toast.error(msg);
        } finally {
            setProfileSaving(false);
        }
    };

    const handleSaveNotifEmail = async (e: React.FormEvent) => {
        e.preventDefault();
        setNotifEmailSaving(true);
        try {
            const updated = await fetchJson<User>('/api/auth/profile/notification-email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: notifEmail.trim() }),
            });
            onUserUpdate(updated);
            toast.success('Notification email updated');
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Failed to update notification email';
            toast.error(msg);
        } finally {
            setNotifEmailSaving(false);
        }
    };

    const handleRemoveNotifEmail = async () => {
        setNotifEmailSaving(true);
        try {
            const updated = await fetchJson<User>('/api/auth/profile/notification-email', {
                method: 'DELETE',
            });
            setNotifEmail('');
            onUserUpdate(updated);
            toast.success('Notification email removed');
        } catch {
            toast.error('Failed to remove notification email');
        } finally {
            setNotifEmailSaving(false);
        }
    };

    const handleSetPassword = async (e: React.FormEvent) => {
        e.preventDefault();
        if (newPassword !== confirmPassword) {
            toast.error('Passwords do not match');
            return;
        }
        if (newPassword.length < 8) {
            toast.error('Password must be at least 8 characters');
            return;
        }
        setPasswordSaving(true);
        try {
            const res = await fetchApi('/api/auth/profile/set-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: newPassword }),
            });
            if (!res.ok) {
                throw new Error(await readApiError(res, 'Failed to set password'));
            }
            toast.success('Password set! You can now log in with your email and password.');
            setNewPassword('');
            setConfirmPassword('');
            // Refresh user to reflect has_password = true
            const refreshed = await fetchJson<User>('/api/auth/me');
            onUserUpdate(refreshed);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : 'Failed to set password';
            toast.error(msg);
        } finally {
            setPasswordSaving(false);
        }
    };

    const handleSendResetLink = async () => {
        setResetLinkSending(true);
        try {
            await fetchApi('/api/auth/email/forgot-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: user.email }),
            });
            toast.success('Password reset link sent — check your inbox.');
        } catch {
            toast.error('Failed to send reset link. Please try again.');
        } finally {
            setResetLinkSending(false);
        }
    };

    const handleConnectGitHub = async () => {
        try {
            const data = await fetchJson<{ authorization_url: string }>('/api/auth/github/link/authorize');
            window.location.href = data.authorization_url;
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to start GitHub connect flow';
            toast.error(message);
        }
    };

    const handleUnlinkGitHub = async () => {
        if (!confirm('Are you sure you want to unlink your GitHub account?')) {
            return;
        }
        try {
            await fetchApi('/api/auth/profile/github', { method: 'DELETE' });
            toast.success('GitHub account unlinked successfully');
            // Refresh user data
            const updated = await fetchJson<User>('/api/auth/me');
            onUserUpdate(updated);
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to unlink GitHub account';
            toast.error(message);
        }
    };

    // Derive initial for avatar placeholder
    const initial = (user.name || user.email).charAt(0).toUpperCase();

    return (
        <div className="min-h-screen bg-background text-foreground">
            {/* Page header */}
            <header className="border-b sticky top-0 bg-background/95 backdrop-blur z-10">
                <div className="flex items-center gap-3 px-4 h-14">
                    <Button variant="ghost" size="icon" onClick={() => navigate('/')}>
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <h1 className="text-lg font-semibold">Account Settings</h1>
                </div>
            </header>

            <main className="max-w-2xl mx-auto px-4 py-8 space-y-8">
                {/* Avatar + overview */}
                <section className="flex items-center gap-4">
                    <div className="h-20 w-20 rounded-full bg-primary/10 text-primary flex items-center justify-center text-3xl font-bold shrink-0">
                        {initial}
                    </div>
                    <div>
                        <p className="text-xl font-semibold">{user.name}</p>
                        <p className="text-sm text-muted-foreground">{user.email}</p>
                        <Badge variant="outline" className="mt-1 capitalize text-xs">{user.role}</Badge>
                    </div>
                </section>

                {/* Profile section */}
                <section className="rounded-lg border p-5 space-y-4">
                    <div className="flex items-center gap-2 mb-1">
                        <UserIcon className="h-4 w-4 text-muted-foreground" />
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Profile</h2>
                    </div>
                    <form onSubmit={handleSaveProfile} className="space-y-4">
                        <div className="space-y-1">
                            <label className="text-sm font-medium" htmlFor="username">
                                Username
                            </label>
                            <div className="relative">
                                <AtSign className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                    id="username"
                                    className="pl-9"
                                    placeholder="your-username"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                    minLength={3}
                                    maxLength={50}
                                />
                            </div>
                            <p className="text-xs text-muted-foreground">
                                3–50 characters. Letters, numbers, underscores, hyphens, and dots only.
                            </p>
                        </div>

                        <div className="space-y-1">
                            <label className="text-sm font-medium" htmlFor="displayName">
                                Display Name
                            </label>
                            <Input
                                id="displayName"
                                placeholder="Your full name"
                                value={displayName}
                                onChange={(e) => setDisplayName(e.target.value)}
                                maxLength={100}
                            />
                        </div>

                        <div className="space-y-1">
                            <label className="text-sm font-medium">Primary Email</label>
                            <Input value={user.email} disabled className="cursor-not-allowed" />
                            <p className="text-xs text-muted-foreground">
                                Your primary email cannot be changed here.
                            </p>
                        </div>

                        <Button type="submit" disabled={profileSaving} className="w-full sm:w-auto">
                            {profileSaving ? 'Saving…' : 'Save Profile'}
                        </Button>
                    </form>
                </section>

                {/* Notification email section */}
                <section className="rounded-lg border p-5 space-y-4">
                    <div className="flex items-center gap-2 mb-1">
                        <Mail className="h-4 w-4 text-muted-foreground" />
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Notification Email</h2>
                    </div>
                    <p className="text-sm text-muted-foreground">
                        Add a secondary email address for notifications. This can be different from your
                        primary email (e.g. your work address) and can also be used to sign in.
                    </p>
                    <form onSubmit={handleSaveNotifEmail} className="space-y-3">
                        <Input
                            type="email"
                            placeholder="work@company.com"
                            value={notifEmail}
                            onChange={(e) => setNotifEmail(e.target.value)}
                        />
                        <div className="flex gap-2">
                            <Button
                                type="submit"
                                disabled={notifEmailSaving || !notifEmail.trim()}
                                className="flex-1 sm:flex-none"
                            >
                                {notifEmailSaving ? 'Saving…' : user.notification_email ? 'Update' : 'Add'}
                            </Button>
                            {user.notification_email && (
                                <Button
                                    type="button"
                                    variant="outline"
                                    disabled={notifEmailSaving}
                                    onClick={handleRemoveNotifEmail}
                                >
                                    Remove
                                </Button>
                            )}
                        </div>
                    </form>
                </section>

                {/* GitHub connection section */}
                {githubClientId && (
                    <section className="rounded-lg border p-5 space-y-3">
                        <div className="flex items-center gap-2 mb-1">
                            <Github className="h-4 w-4 text-muted-foreground" />
                            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">GitHub</h2>
                        </div>
                        {user.github_connected ? (
                            <div className="space-y-2">
                                <div className="flex items-center gap-2 text-green-700 dark:text-green-400">
                                    <CheckCircle2 className="h-5 w-5 shrink-0" />
                                    <span className="text-sm font-medium">GitHub account linked</span>
                                </div>
                                {user.github_email && (
                                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                        <Mail className="h-4 w-4 shrink-0" />
                                        <span>{user.github_email}</span>
                                    </div>
                                )}
                                <Button variant="destructive" size="sm" onClick={handleUnlinkGitHub} className="w-full sm:w-auto">
                                    <XCircle className="h-4 w-4 mr-2" />
                                    Unlink GitHub Account
                                </Button>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                <div className="flex items-center gap-2 text-muted-foreground">
                                    <AlertCircle className="h-5 w-5 shrink-0" />
                                    <span className="text-sm">No GitHub account linked</span>
                                </div>
                                <Button variant="outline" onClick={handleConnectGitHub} className="w-full sm:w-auto">
                                    <Github className="h-4 w-4 mr-2" />
                                    Connect GitHub Account
                                </Button>
                                <p className="text-xs text-muted-foreground leading-snug">
                                    Linking GitHub grants designer access and enables GitHub repository browsing.
                                </p>
                            </div>
                        )}
                    </section>
                )}

                {/* Set password section – only shown to GitHub-only users */}
                {!user.has_password && (
                    <section className="rounded-lg border p-5 space-y-4">
                        <div className="flex items-center gap-2 mb-1">
                            <Lock className="h-4 w-4 text-muted-foreground" />
                            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Set a Password</h2>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            Your account was created without a password (e.g. via GitHub). You can set a
                            password now so you can also log in with your email address.
                        </p>
                        <form onSubmit={handleSetPassword} className="space-y-3">
                            <div className="space-y-1">
                                <label className="text-sm font-medium" htmlFor="newPassword">New Password</label>
                                <Input
                                    id="newPassword"
                                    type="password"
                                    placeholder="At least 8 characters"
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    minLength={8}
                                    required
                                />
                            </div>
                            <div className="space-y-1">
                                <label className="text-sm font-medium" htmlFor="confirmPassword">Confirm Password</label>
                                <Input
                                    id="confirmPassword"
                                    type="password"
                                    placeholder="Repeat password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    minLength={8}
                                    required
                                />
                            </div>
                            <Button
                                type="submit"
                                disabled={passwordSaving || !newPassword || !confirmPassword}
                                className="w-full sm:w-auto"
                            >
                                {passwordSaving ? 'Setting password…' : 'Set Password'}
                            </Button>
                        </form>
                    </section>
                )}

                {/* Change password section – shown to users who already have a password */}
                {user.has_password && (
                    <section className="rounded-lg border p-5 space-y-3">
                        <div className="flex items-center gap-2 mb-1">
                            <Lock className="h-4 w-4 text-muted-foreground" />
                            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Password</h2>
                        </div>
                        <div className="flex items-center gap-2 text-green-700 dark:text-green-400 mb-2">
                            <CheckCircle2 className="h-4 w-4 shrink-0" />
                            <span className="text-sm">Password is set</span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            Send a reset link to your primary email to change your password.
                        </p>
                        <Button
                            variant="outline"
                            onClick={handleSendResetLink}
                            disabled={resetLinkSending}
                            className="w-full sm:w-auto"
                        >
                            <RefreshCw className={`h-4 w-4 mr-2 ${resetLinkSending ? 'animate-spin' : ''}`} />
                            {resetLinkSending ? 'Sending…' : 'Send Reset Link'}
                        </Button>
                    </section>
                )}
            </main>
        </div>
    );
}

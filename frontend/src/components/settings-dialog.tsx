import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { GitBranch, Copy, Shield, Plus, Trash2, Clock, Users, Settings2, CheckCircle, XCircle, Mail, Loader2 } from "lucide-react";
import { User, UserRole } from "@/types/auth";
import { fetchApi, readApiError } from "@/lib/api";

interface SettingsDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    user: User | null;
}

type SettingsTab = "git" | "access" | "pending" | "users" | "system";

interface RoleAssignment {
    email: string;
    role: UserRole;
    source: string;
}

interface PendingUser {
    email: string;
    registered_at: string;
}

interface RegisteredUser {
    email: string;
    is_active: boolean;
    is_verified: boolean;
    role: string | null;
}

export function SettingsDialog({ open, onOpenChange, user }: SettingsDialogProps) {
    const [activeTab, setActiveTab] = useState<SettingsTab>("git");
    const [pendingCount, setPendingCount] = useState(0);
    const isAdmin = user?.role === "admin";

    useEffect(() => {
        if (open && isAdmin) {
            fetchApi("/api/settings/pending-users")
                .then((r) => (r.ok ? r.json() : []))
                .then((data: PendingUser[]) => setPendingCount(data.length))
                .catch(() => {});
        }
    }, [open, isAdmin]);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-4xl p-0 overflow-hidden flex h-[600px]">
                <DialogTitle className="sr-only">Workspace Settings</DialogTitle>
                <DialogDescription className="sr-only">
                    Manage Git, SSH, and access control settings for this workspace.
                </DialogDescription>
                <div className="w-64 bg-muted/30 border-r p-4 flex flex-col gap-2">
                    <div className="mb-4 px-2">
                        <h2 className="text-lg font-semibold tracking-tight">Settings</h2>
                        <p className="text-sm text-muted-foreground">Manage your workspace</p>
                    </div>

                    <Button
                        variant={activeTab === "git" ? "secondary" : "ghost"}
                        className="justify-start"
                        onClick={() => setActiveTab("git")}
                    >
                        <GitBranch className="mr-2 h-4 w-4" />
                        Git & SSH
                    </Button>

                    <Button
                        variant={activeTab === "access" ? "secondary" : "ghost"}
                        className="justify-start"
                        onClick={() => setActiveTab("access")}
                    >
                        <Shield className="mr-2 h-4 w-4" />
                        Access Control
                    </Button>

                    {isAdmin && (
                        <Button
                            variant={activeTab === "pending" ? "secondary" : "ghost"}
                            className="justify-start relative"
                            onClick={() => setActiveTab("pending")}
                        >
                            <Clock className="mr-2 h-4 w-4" />
                            Pending Approvals
                            {pendingCount > 0 && (
                                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
                                    {pendingCount > 9 ? "9+" : pendingCount}
                                </span>
                            )}
                        </Button>
                    )}

                    {isAdmin && (
                        <Button
                            variant={activeTab === "users" ? "secondary" : "ghost"}
                            className="justify-start"
                            onClick={() => setActiveTab("users")}
                        >
                            <Users className="mr-2 h-4 w-4" />
                            Users
                        </Button>
                    )}

                    {isAdmin && (
                        <Button
                            variant={activeTab === "system" ? "secondary" : "ghost"}
                            className="justify-start"
                            onClick={() => setActiveTab("system")}
                        >
                            <Settings2 className="mr-2 h-4 w-4" />
                            System
                        </Button>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto p-6">
                    {activeTab === "git" && <GitSettings user={user} />}
                    {activeTab === "access" && <AccessControlSettings isAdmin={isAdmin} />}
                    {activeTab === "pending" && <PendingApprovalsSettings onCountChange={setPendingCount} />}
                    {activeTab === "users" && <UsersSettings />}
                    {activeTab === "system" && <SystemSettings user={user} />}
                </div>
            </DialogContent>
        </Dialog>
    );
}

function GitSettings({ user }: { user: User | null }) {
    const [sshKey, setSshKey] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [email] = useState(user?.email || "kicad-prism@example.com");

    const fetchSshKey = useCallback(async (signal?: AbortSignal) => {
        setLoading(true);
        try {
            const res = await fetchApi("/api/settings/ssh-key", { signal });
            if (res.ok) {
                const data = await res.json();
                setSshKey(data.public_key);
            }
        } catch (err) {
            if (err instanceof DOMException && err.name === "AbortError") {
                return;
            }
            console.error("Failed to fetch SSH key", err);
            toast.error("Failed to load SSH key settings");
        } finally {
            if (!signal?.aborted) {
                setLoading(false);
            }
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        void fetchSshKey(controller.signal);
        return () => controller.abort();
    }, [fetchSshKey]);

    const generateKey = async () => {
        if (!window.confirm("This will overwrite any existing SSH key. Continue?")) return;

        setGenerating(true);
        try {
            const res = await fetchApi("/api/settings/ssh-key/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email }),
            });
            if (res.ok) {
                const data = await res.json();
                setSshKey(data.public_key);
                toast.success("New SSH key generated successfully");
            } else {
                toast.error(await readApiError(res, "Failed to generate SSH key."));
            }
        } catch {
            toast.error("An error occurred while connecting to the backend.");
        } finally {
            setGenerating(false);
        }
    };

    const copyToClipboard = () => {
        if (sshKey) {
            void navigator.clipboard.writeText(sshKey);
            toast.success("SSH Key copied to clipboard");
        }
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">Git Configuration</h3>
                <p className="text-sm text-muted-foreground">
                    Manage your SSH keys for authenticating with Git providers like GitHub and GitLab.
                </p>
            </div>

            <div className="space-y-4 border rounded-lg p-4 bg-card">
                <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                        <Label className="text-base">SSH Key</Label>
                        <p className="text-sm text-muted-foreground">
                            Your public SSH key for identifying this workspace.
                        </p>
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={generateKey}
                        disabled={generating}
                    >
                        {generating ? "Generating..." : "Generate New Key"}
                    </Button>
                </div>

                {loading ? (
                    <div className="h-24 bg-muted animate-pulse rounded-md" />
                ) : sshKey ? (
                    <div className="relative">
                        <Textarea
                            readOnly
                            value={sshKey}
                            className="font-mono text-xs resize-none h-24 bg-muted/50 pr-10"
                        />
                        <Button
                            size="icon"
                            variant="ghost"
                            className="absolute top-2 right-2 h-8 w-8"
                            onClick={copyToClipboard}
                            title="Copy to clipboard"
                        >
                            <Copy className="h-4 w-4" />
                        </Button>
                    </div>
                ) : (
                    <div className="text-sm text-muted-foreground italic border border-dashed p-4 rounded-md text-center">
                        No SSH key found. Click "Generate New Key" to create one.
                    </div>
                )}
            </div>
        </div>
    );
}

function AccessControlSettings({ isAdmin }: { isAdmin: boolean }) {
    const [loading, setLoading] = useState(false);
    const [assignments, setAssignments] = useState<RoleAssignment[]>([]);
    const [newEmail, setNewEmail] = useState("");
    const [newRole, setNewRole] = useState<UserRole>("viewer");

    const loadAssignments = useCallback(async () => {
        if (!isAdmin) {
            setAssignments([]);
            return;
        }

        setLoading(true);
        try {
            const response = await fetchApi("/api/settings/access/users");
            if (!response.ok) {
                throw new Error(await readApiError(response, "Failed to load role assignments"));
            }
            const data = (await response.json()) as RoleAssignment[];
            setAssignments(data);
        } catch (error) {
            const message = error instanceof Error ? error.message : "Failed to load role assignments";
            toast.error(message);
        } finally {
            setLoading(false);
        }
    }, [isAdmin]);

    useEffect(() => {
        void loadAssignments();
    }, [loadAssignments]);

    const upsertRole = async (email: string, role: UserRole) => {
        const normalizedEmail = email.trim().toLowerCase();
        if (!normalizedEmail) {
            toast.error("Email is required");
            return;
        }
        try {
            const response = await fetchApi(`/api/settings/access/users/${encodeURIComponent(normalizedEmail)}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ role }),
            });
            if (!response.ok) {
                throw new Error(await readApiError(response, "Failed to update role assignment"));
            }
            toast.success("Role assignment updated");
            setNewEmail("");
            setNewRole("viewer");
            await loadAssignments();
        } catch (error) {
            const message = error instanceof Error ? error.message : "Failed to update role assignment";
            toast.error(message);
        }
    };

    const removeRole = async (email: string) => {
        if (!window.confirm(`Remove role assignment for ${email}?`)) {
            return;
        }

        try {
            const response = await fetchApi(`/api/settings/access/users/${encodeURIComponent(email)}`, {
                method: "DELETE",
            });
            if (!response.ok) {
                throw new Error(await readApiError(response, "Failed to remove role assignment"));
            }
            toast.success("Role assignment removed");
            await loadAssignments();
        } catch (error) {
            const message = error instanceof Error ? error.message : "Failed to remove role assignment";
            toast.error(message);
        }
    };

    if (!isAdmin) {
        return (
            <div className="rounded-lg border border-border p-4 text-sm text-muted-foreground">
                Admin role is required to view and manage user access.
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">Access Control</h3>
                <p className="text-sm text-muted-foreground">
                    Manage role assignments for workspace users.
                </p>
            </div>

            <div className="rounded-lg border p-4 space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr_auto] gap-2">
                    <Input
                        placeholder="user@example.com"
                        value={newEmail}
                        onChange={(event) => setNewEmail(event.target.value)}
                    />
                    <select
                        className="h-10 rounded-md border bg-background px-3 text-sm"
                        value={newRole}
                        onChange={(event) => setNewRole(event.target.value as UserRole)}
                    >
                        <option value="viewer">viewer</option>
                        <option value="designer">designer</option>
                        <option value="admin">admin</option>
                    </select>
                    <Button onClick={() => void upsertRole(newEmail, newRole)}>
                        <Plus className="h-4 w-4 mr-2" />
                        Add / Update
                    </Button>
                </div>
            </div>

            <div className="rounded-lg border overflow-hidden">
                <div className="grid grid-cols-[2fr_1fr_1fr_auto] border-b bg-muted/30 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <div>Email</div>
                    <div>Role</div>
                    <div>Source</div>
                    <div />
                </div>
                {loading ? (
                    <div className="p-4 text-sm text-muted-foreground">Loading assignments...</div>
                ) : assignments.length === 0 ? (
                    <div className="p-4 text-sm text-muted-foreground">No role assignments found.</div>
                ) : (
                    assignments.map((assignment) => {
                        const isBootstrap = assignment.source === "bootstrap";
                        return (
                            <div
                                key={assignment.email}
                                className="grid grid-cols-[2fr_1fr_1fr_auto] items-center border-b px-4 py-2 gap-2"
                            >
                                <div className="truncate text-sm">{assignment.email}</div>
                                <select
                                    className="h-8 rounded-md border bg-background px-2 text-sm"
                                    value={assignment.role}
                                    disabled={isBootstrap}
                                    onChange={(event) =>
                                        void upsertRole(assignment.email, event.target.value as UserRole)
                                    }
                                >
                                    <option value="viewer">viewer</option>
                                    <option value="designer">designer</option>
                                    <option value="admin">admin</option>
                                </select>
                                <div className="text-sm text-muted-foreground">{assignment.source}</div>
                                <div className="flex justify-end">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        disabled={isBootstrap}
                                        onClick={() => void removeRole(assignment.email)}
                                        aria-label={`Remove role assignment for ${assignment.email}`}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}

function PendingApprovalsSettings({ onCountChange }: { onCountChange: (n: number) => void }) {
    const [pending, setPending] = useState<PendingUser[]>([]);
    const [loading, setLoading] = useState(false);
    const [actioning, setActioning] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await fetchApi("/api/settings/pending-users");
            if (res.ok) {
                const data = (await res.json()) as PendingUser[];
                setPending(data);
                onCountChange(data.length);
            }
        } finally {
            setLoading(false);
        }
    }, [onCountChange]);

    useEffect(() => { void load(); }, [load]);

    const approve = async (email: string) => {
        setActioning(email);
        try {
            const res = await fetchApi(`/api/settings/pending-users/${encodeURIComponent(email)}/approve`, { method: "POST" });
            if (res.ok) {
                toast.success(`Approved ${email}`);
                await load();
            } else {
                toast.error(await readApiError(res, "Failed to approve"));
            }
        } finally {
            setActioning(null);
        }
    };

    const deny = async (email: string) => {
        if (!window.confirm(`Deny registration for ${email}? A denial email will be sent.`)) return;
        setActioning(email);
        try {
            const res = await fetchApi(`/api/settings/pending-users/${encodeURIComponent(email)}/deny`, { method: "POST" });
            if (res.ok) {
                toast.success(`Denied ${email}`);
                await load();
            } else {
                toast.error(await readApiError(res, "Failed to deny"));
            }
        } finally {
            setActioning(null);
        }
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">Pending Approvals</h3>
                <p className="text-sm text-muted-foreground">
                    Users who have registered but whose email domain is not on the whitelist.
                </p>
            </div>
            <div className="rounded-lg border overflow-hidden">
                <div className="grid grid-cols-[2fr_1fr_auto] border-b bg-muted/30 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <div>Email</div>
                    <div>Registered</div>
                    <div />
                </div>
                {loading ? (
                    <div className="p-4 text-sm text-muted-foreground">Loading...</div>
                ) : pending.length === 0 ? (
                    <div className="p-4 text-sm text-muted-foreground">No pending approvals.</div>
                ) : (
                    pending.map((p) => (
                        <div key={p.email} className="grid grid-cols-[2fr_1fr_auto] items-center border-b px-4 py-2 gap-2">
                            <div className="truncate text-sm">{p.email}</div>
                            <div className="text-xs text-muted-foreground">
                                {p.registered_at ? new Date(p.registered_at).toLocaleDateString() : "—"}
                            </div>
                            <div className="flex gap-1">
                                <Button
                                    size="sm"
                                    className="h-7 text-xs"
                                    disabled={actioning === p.email}
                                    onClick={() => void approve(p.email)}
                                >
                                    <CheckCircle className="h-3.5 w-3.5 mr-1" />
                                    Approve
                                </Button>
                                <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 text-xs text-destructive hover:text-destructive"
                                    disabled={actioning === p.email}
                                    onClick={() => void deny(p.email)}
                                >
                                    <XCircle className="h-3.5 w-3.5 mr-1" />
                                    Deny
                                </Button>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}

function UsersSettings() {
    const [users, setUsers] = useState<RegisteredUser[]>([]);
    const [loading, setLoading] = useState(false);
    const [resending, setResending] = useState<string | null>(null);
    const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
    const [deleting, setDeleting] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await fetchApi("/api/settings/users");
            if (res.ok) {
                const data = (await res.json()) as RegisteredUser[];
                setUsers(data);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        setDeleting(true);
        try {
            const res = await fetchApi(`/api/settings/users/${encodeURIComponent(deleteTarget)}`, { method: "DELETE" });
            if (res.ok) {
                toast.success(`Deleted ${deleteTarget}`);
                setDeleteTarget(null);
                void load();
            } else {
                toast.error(await readApiError(res, "Failed to delete user"));
            }
        } finally {
            setDeleting(false);
        }
    };

    const resendVerification = async (email: string) => {
        setResending(email);
        try {
            const res = await fetchApi(
                `/api/settings/users/${encodeURIComponent(email)}/resend-verification`,
                { method: "POST" }
            );
            if (res.ok) {
                toast.success(`Verification email sent to ${email}`);
            } else {
                toast.error(await readApiError(res, "Failed to resend verification email"));
            }
        } finally {
            setResending(null);
        }
    };

    return (
        <div className="space-y-6">
            {deleteTarget && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="bg-background rounded-lg shadow-xl p-6 w-96 space-y-4">
                        <h3 className="font-semibold text-lg">Delete User</h3>
                        <p className="text-sm text-muted-foreground">
                            Permanently delete <strong className="text-foreground">{deleteTarget}</strong>? This cannot be undone.
                        </p>
                        <div className="flex justify-end gap-2">
                            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
                            <Button variant="destructive" onClick={() => void confirmDelete()} disabled={deleting}>
                                {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 mr-1.5" />}
                                Delete
                            </Button>
                        </div>
                    </div>
                </div>
            )}
            <div>
                <h3 className="text-lg font-medium">Registered Users</h3>
                <p className="text-sm text-muted-foreground">All accounts in the system.</p>
            </div>
            <div className="rounded-lg border overflow-hidden">
                <div className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] border-b bg-muted/30 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <div>Email</div>
                    <div>Role</div>
                    <div>Verified</div>
                    <div>Active</div>
                    <div />
                </div>
                {loading ? (
                    <div className="p-4 text-sm text-muted-foreground">Loading users...</div>
                ) : users.length === 0 ? (
                    <div className="p-4 text-sm text-muted-foreground">No users found.</div>
                ) : (
                    users.map((u) => (
                        <div key={u.email} className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] items-center border-b px-4 py-2 gap-2">
                            <div className="truncate text-sm">{u.email}</div>
                            <div className="text-sm">
                                {u.role ? (
                                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{u.role}</span>
                                ) : (
                                    <span className="text-xs text-muted-foreground italic">none</span>
                                )}
                            </div>
                            <div>
                                {u.is_verified
                                    ? <CheckCircle className="h-4 w-4 text-green-500" />
                                    : <XCircle className="h-4 w-4 text-muted-foreground" />}
                            </div>
                            <div>
                                {u.is_active
                                    ? <CheckCircle className="h-4 w-4 text-green-500" />
                                    : <XCircle className="h-4 w-4 text-destructive" />}
                            </div>
                            <div className="flex items-center justify-end gap-1.5">
                                {!u.is_verified && (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="h-7 text-xs"
                                        disabled={resending === u.email}
                                        onClick={() => void resendVerification(u.email)}
                                        title="Resend verification email"
                                    >
                                        {resending === u.email
                                            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                            : <Mail className="h-3.5 w-3.5" />}
                                        <span className="ml-1">Resend</span>
                                    </Button>
                                )}
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
                                    onClick={() => setDeleteTarget(u.email)}
                                    title="Delete user"
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}

function SystemSettings({ user }: { user: User | null }) {
    const [isTesting, setIsTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

    const testSmtp = async () => {
        setIsTesting(true);
        setTestResult(null);
        try {
            const res = await fetchApi("/api/settings/smtp/test", { method: "POST" });
            const data = await res.json();
            if (!res.ok) {
                setTestResult({ success: false, message: data.detail || "Failed to send test email" });
            } else {
                setTestResult({ success: true, message: data.message || `Test email sent to ${user?.email}` });
            }
        } catch {
            setTestResult({ success: false, message: "Network error — could not reach the server" });
        } finally {
            setIsTesting(false);
        }
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-lg font-medium">System</h3>
                <p className="text-sm text-muted-foreground">Server diagnostics and configuration tools.</p>
            </div>
            <div className="space-y-4 border rounded-lg p-4 bg-card">
                <div className="space-y-0.5">
                    <Label className="text-base">SMTP Email Test</Label>
                    <p className="text-sm text-muted-foreground">
                        Send a test email to <strong>{user?.email}</strong> to verify outgoing mail is working.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Button variant="outline" onClick={testSmtp} disabled={isTesting}>
                        {isTesting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Mail className="mr-2 h-4 w-4" />}
                        Send Test Email
                    </Button>
                    {testResult && (
                        <span className={`text-sm ${testResult.success ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
                            {testResult.message}
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}

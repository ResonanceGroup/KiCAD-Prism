import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
    Users, UserPlus, Trash2, Loader2, Settings2,
    Globe, Lock, EyeOff, CheckCircle, XCircle, ShieldCheck, Search, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { fetchApi, readApiError } from "@/lib/api";
import type { User } from "@/types/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Member {
    project_id: string;
    user_email: string;
    project_role: string;
    added_by: string;
    added_at: string;
}

interface AccessRequest {
    id: string;
    project_id: string;
    user_email: string;
    requested_role: string;
    status: string;
    requested_at: string;
}

type SubTab = "members" | "general";

// ---------------------------------------------------------------------------
// Role badge helper
// ---------------------------------------------------------------------------

const ROLE_COLORS: Record<string, string> = {
    admin:   "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30",
    manager: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30",
    viewer:  "bg-muted text-muted-foreground border-border",
};

function RoleBadge({ role }: { role: string }) {
    return (
        <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium capitalize", ROLE_COLORS[role] ?? ROLE_COLORS.viewer)}>
            {role}
        </span>
    );
}

// ---------------------------------------------------------------------------
// Invite dialog
// ---------------------------------------------------------------------------

const UAC_ROLE_COLORS: Record<string, string> = {
    admin:    "bg-red-500/15 text-red-600 border border-red-300",
    designer: "bg-blue-500/15 text-blue-600 border border-blue-300",
    viewer:   "bg-gray-500/15 text-gray-600 border border-gray-300",
};

/** Default project role granted given a workspace UAC role. */
function defaultProjectRole(uacRole: string): "viewer" | "manager" | "admin" {
    if (uacRole === "admin")    return "admin";
    if (uacRole === "designer") return "manager";
    return "viewer";
}

interface WorkspaceUser {
    email: string;
    role: string;
}

interface InviteDialogProps {
    projectId: string;
    currentMemberEmails: string[];
    onClose: () => void;
    onSuccess: () => void;
}

function InviteDialog({ projectId, currentMemberEmails, onClose, onSuccess }: InviteDialogProps) {
    const [users, setUsers] = useState<WorkspaceUser[]>([]);
    const [search, setSearch] = useState("");
    const [inviting, setInviting] = useState<string | null>(null);
    const [invited, setInvited] = useState<Set<string>>(new Set());
    const [loadingUsers, setLoadingUsers] = useState(true);

    useEffect(() => {
        void fetchApi("/api/auth/users")
            .then((r) => (r.ok ? r.json() : []))
            .then((data: WorkspaceUser[]) => {
                setUsers(data);
                setLoadingUsers(false);
            });
    }, []);

    const memberSet = new Set(currentMemberEmails.map((e) => e.toLowerCase()));

    const filtered = users.filter(
        (u) => !search || u.email.toLowerCase().includes(search.toLowerCase())
    );

    const sendInvite = async (u: WorkspaceUser) => {
        setInviting(u.email);
        try {
            const res = await fetchApi(`/api/projects/${projectId}/invite`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    invited_email: u.email,
                    invited_role: defaultProjectRole(u.role),
                }),
            });
            if (!res.ok) {
                toast.error(await readApiError(res, "Failed to send invite"));
                return;
            }
            toast.success(`Invite sent to ${u.email}`);
            setInvited((prev) => new Set(prev).add(u.email));
            onSuccess();
        } finally {
            setInviting(null);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-background rounded-lg shadow-xl p-6 w-[480px] space-y-4 max-h-[80vh] flex flex-col">
                <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-lg flex items-center gap-2">
                        <UserPlus className="h-5 w-5" /> Invite Member
                    </h3>
                    <Button variant="ghost" size="sm" onClick={onClose}>✕</Button>
                </div>

                {/* Search */}
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                    <Input
                        className="pl-9"
                        placeholder="Search workspace users…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        autoFocus
                    />
                </div>

                {/* User list */}
                <div className="overflow-y-auto flex-1 border rounded-md divide-y">
                    {loadingUsers && (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                    )}
                    {!loadingUsers && filtered.length === 0 && (
                        <p className="px-4 py-6 text-sm text-center text-muted-foreground">No users found</p>
                    )}
                    {!loadingUsers && filtered.map((u) => {
                        const isMember  = memberSet.has(u.email.toLowerCase());
                        const isInvited = invited.has(u.email);
                        const isLoading = inviting === u.email;
                        return (
                            <div key={u.email} className="flex items-center gap-3 px-4 py-2.5">
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm truncate">{u.email}</p>
                                </div>
                                <span className={cn(
                                    "text-xs px-2 py-0.5 rounded-full font-medium capitalize shrink-0",
                                    UAC_ROLE_COLORS[u.role] ?? UAC_ROLE_COLORS.viewer
                                )}>
                                    {u.role}
                                </span>
                                {isMember ? (
                                    <span className="text-xs text-muted-foreground shrink-0">Already a member</span>
                                ) : isInvited ? (
                                    <span className="text-xs text-green-600 shrink-0">Invited ✓</span>
                                ) : (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-7 text-xs shrink-0"
                                        disabled={!!inviting}
                                        onClick={() => void sendInvite(u)}
                                    >
                                        {isLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Invite"}
                                    </Button>
                                )}
                            </div>
                        );
                    })}
                </div>

                <div className="flex justify-end">
                    <Button variant="outline" onClick={onClose}>Close</Button>
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Members sub-tab
// ---------------------------------------------------------------------------

function MembersSubTab({ projectId, user }: { projectId: string; user: User | null }) {
    const [members, setMembers] = useState<Member[]>([]);
    const [requests, setRequests] = useState<AccessRequest[]>([]);
    const [loading, setLoading] = useState(true);
    const [showInvite, setShowInvite] = useState(false);
    const [removingEmail, setRemovingEmail] = useState<string | null>(null);
    const [promotingEmail, setPromotingEmail] = useState<string | null>(null);
    const [approvingId, setApprovingId] = useState<string | null>(null);
    const [denyingId, setDenyingId] = useState<string | null>(null);

    const myEmail = user?.email?.toLowerCase() ?? "";

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [membRes, reqRes] = await Promise.allSettled([
                fetchApi(`/api/projects/${projectId}/members`),
                fetchApi(`/api/projects/${projectId}/access-requests`),
            ]);
            if (membRes.status === "fulfilled" && membRes.value.ok) {
                setMembers(await membRes.value.json());
            }
            if (reqRes.status === "fulfilled" && reqRes.value.ok) {
                setRequests(await reqRes.value.json());
            }
        } finally {
            setLoading(false);
        }
    }, [projectId]);

    useEffect(() => { void load(); }, [load]);

    const myRole = members.find((m) => m.user_email.toLowerCase() === myEmail)?.project_role ?? null;
    const canManage = myRole === "manager" || myRole === "admin";

    const changeRole = async (email: string, newRole: string) => {
        setPromotingEmail(email);
        try {
            const res = await fetchApi(
                `/api/projects/${projectId}/members/${encodeURIComponent(email)}/role`,
                {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ project_role: newRole }),
                },
            );
            if (res.ok) {
                toast.success(`Role updated to ${newRole}`);
                void load();
            } else {
                toast.error(await readApiError(res, "Failed to update role"));
            }
        } finally {
            setPromotingEmail(null);
        }
    };

    const removeMember = async (email: string) => {
        setRemovingEmail(email);
        try {
            const res = await fetchApi(`/api/projects/${projectId}/members/${encodeURIComponent(email)}`, { method: "DELETE" });
            if (res.ok) {
                toast.success(`Removed ${email}`);
                void load();
            } else {
                toast.error(await readApiError(res, "Failed to remove member"));
            }
        } finally {
            setRemovingEmail(null);
        }
    };

    const resolveRequest = async (id: string, action: "approve" | "deny") => {
        if (action === "approve") setApprovingId(id); else setDenyingId(id);
        try {
            const res = await fetchApi(`/api/projects/${projectId}/access-requests/${id}/${action}`, { method: "POST" });
            if (res.ok) {
                toast.success(action === "approve" ? "Request approved" : "Request denied");
                void load();
            } else {
                toast.error(await readApiError(res, "Failed"));
            }
        } finally {
            setApprovingId(null);
            setDenyingId(null);
        }
    };

    if (loading) {
        return (
            <div className="flex h-48 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <>
            {showInvite && (
                <InviteDialog
                    projectId={projectId}
                    currentMemberEmails={members.map((m) => m.user_email)}
                    onClose={() => setShowInvite(false)}
                    onSuccess={() => void load()}
                />
            )}

            <div className="space-y-8">
                {/* Members */}
                <section>
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground">
                            Members ({members.length})
                        </h3>
                        {canManage && (
                            <Button size="sm" onClick={() => setShowInvite(true)}>
                                <UserPlus className="h-3.5 w-3.5 mr-1.5" />
                                Invite
                            </Button>
                        )}
                    </div>

                    <div className="rounded-lg border overflow-hidden">
                        <div className="grid grid-cols-[1fr_auto_auto] gap-3 border-b bg-muted/30 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            <div>Email</div>
                            <div>Role</div>
                            <div />
                        </div>
                        {members.length === 0 ? (
                            <div className="px-4 py-6 text-sm text-muted-foreground text-center">No members yet.</div>
                        ) : (
                            members.map((m) => (
                                <div key={m.user_email} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-4 py-2.5 border-b last:border-b-0">
                                    <div className="text-sm truncate">
                                        {m.user_email}
                                        {m.user_email.toLowerCase() === myEmail && (
                                            <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                                        )}
                                    </div>
                                    {canManage ? (
                                        <div className="relative flex items-center">
                                            {promotingEmail === m.user_email && (
                                                <Loader2 className="absolute left-2 h-3 w-3 animate-spin text-muted-foreground pointer-events-none" />
                                            )}
                                            <select
                                                value={m.project_role}
                                                disabled={promotingEmail === m.user_email}
                                                onChange={(e) => void changeRole(m.user_email, e.target.value)}
                                                className="h-7 rounded-md border border-input bg-background pl-2 pr-6 text-xs font-medium capitalize focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 cursor-pointer"
                                            >
                                                <option value="viewer">viewer</option>
                                                <option value="manager">manager</option>
                                                <option value="admin">admin</option>
                                            </select>
                                        </div>
                                    ) : (
                                        <RoleBadge role={m.project_role} />
                                    )}
                                    <div className="w-8 flex justify-end">
                                        {canManage && m.user_email.toLowerCase() !== myEmail && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10"
                                                disabled={removingEmail === m.user_email}
                                                onClick={() => void removeMember(m.user_email)}
                                                title="Remove member"
                                            >
                                                {removingEmail === m.user_email
                                                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                                    : <Trash2 className="h-3.5 w-3.5" />}
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </section>

                {/* Pending Access Requests */}
                {canManage && requests.length > 0 && (
                    <section>
                        <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground mb-3">
                            Access Requests ({requests.length})
                        </h3>
                        <div className="rounded-lg border overflow-hidden">
                            {requests.map((r) => (
                                <div key={r.id} className="flex items-center gap-3 px-4 py-3 border-b last:border-b-0">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate">{r.user_email}</p>
                                        <p className="text-xs text-muted-foreground">
                                            Requesting: <span className="capitalize font-medium">{r.requested_role}</span>
                                        </p>
                                    </div>
                                    <div className="flex gap-2 shrink-0">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="h-7 text-green-600 border-green-500/40 hover:bg-green-500/10"
                                            disabled={approvingId === r.id || denyingId === r.id}
                                            onClick={() => void resolveRequest(r.id, "approve")}
                                        >
                                            {approvingId === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle className="h-3.5 w-3.5 mr-1" />}
                                            Approve
                                        </Button>
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            className="h-7 text-destructive border-destructive/40 hover:bg-destructive/10"
                                            disabled={approvingId === r.id || denyingId === r.id}
                                            onClick={() => void resolveRequest(r.id, "deny")}
                                        >
                                            {denyingId === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <XCircle className="h-3.5 w-3.5 mr-1" />}
                                            Deny
                                        </Button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                {!canManage && (
                    <p className="text-sm text-muted-foreground">
                        Only project managers and admins can invite members or manage access.
                    </p>
                )}
            </div>
        </>
    );
}

// ---------------------------------------------------------------------------
// General sub-tab (visibility)
// ---------------------------------------------------------------------------

const VISIBILITY_OPTIONS = [
    { value: "public",  label: "Public",  icon: Globe,   desc: "Visible to all users; designers/admins auto-get view access." },
    { value: "private", label: "Private", icon: Lock,    desc: "Only invited members can see this project." },
    { value: "hidden",  label: "Hidden",  icon: EyeOff,  desc: "Does not appear in Discover; only explicit members can access it." },
] as const;

function GeneralSubTab({ projectId, userEmail }: { projectId: string; userEmail: string }) {
    const navigate = useNavigate();
    const [visibility, setVisibility] = useState<string | null>(null);
    const [projectRole, setProjectRole] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [deleting, setDeleting] = useState(false);

    useEffect(() => {
        void fetchApi(`/api/projects/${projectId}/overview`)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (d?.visibility) setVisibility(d.visibility); });

        void fetchApi(`/api/projects/${projectId}/members`)
            .then((r) => (r.ok ? r.json() : []))
            .then((members: Array<{ user_email: string; project_role: string }>) => {
                const me = members.find((m) => m.user_email.toLowerCase() === userEmail.toLowerCase());
                setProjectRole(me?.project_role ?? null);
            });
    }, [projectId, userEmail]);

    const save = async (v: string) => {
        setSaving(true);
        try {
            const res = await fetchApi(`/api/projects/${projectId}/visibility`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ visibility: v }),
            });
            if (res.ok) {
                setVisibility(v);
                toast.success("Visibility updated");
            } else {
                toast.error(await readApiError(res, "Failed to update visibility"));
            }
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        setDeleting(true);
        try {
            const res = await fetchApi(`/api/projects/${projectId}`, { method: "DELETE" });
            if (res.ok) {
                toast.success("Project removed from server");
                navigate("/");
            } else {
                toast.error(await readApiError(res, "Failed to delete project"));
                setConfirmDelete(false);
            }
        } finally {
            setDeleting(false);
        }
    };

    return (
        <div className="space-y-6 max-w-lg">
            <div>
                <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground mb-3">
                    Project Visibility
                </h3>
                <div className="space-y-2">
                    {VISIBILITY_OPTIONS.map(({ value, label, icon: Icon, desc }) => (
                        <button
                            key={value}
                            className={cn(
                                "w-full flex items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors",
                                visibility === value
                                    ? "border-primary bg-primary/5"
                                    : "hover:bg-muted/40",
                            )}
                            onClick={() => void save(value)}
                            disabled={saving || visibility === value}
                        >
                            <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", visibility === value ? "text-primary" : "text-muted-foreground")} />
                            <div>
                                <p className={cn("text-sm font-medium", visibility === value ? "text-primary" : "")}>{label}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
                            </div>
                            {visibility === value && (
                                <ShieldCheck className="h-4 w-4 text-primary ml-auto shrink-0 mt-0.5" />
                            )}
                        </button>
                    ))}
                </div>
            </div>

            {/* Danger zone — project admins only */}
            {projectRole === "admin" && (
                <div className="rounded-lg border border-destructive/40 p-4">
                    <h3 className="font-semibold text-sm uppercase tracking-wide text-destructive mb-1">
                        Danger Zone
                    </h3>
                    <p className="text-xs text-muted-foreground mb-3">
                        Removes this project from the server. The GitHub repository is not affected.
                        This action cannot be undone.
                    </p>
                    {!confirmDelete ? (
                        <Button
                            variant="outline"
                            size="sm"
                            className="border-destructive/50 text-destructive hover:bg-destructive/10"
                            onClick={() => setConfirmDelete(true)}
                        >
                            <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                            Remove from Server
                        </Button>
                    ) : (
                        <div className="rounded-md bg-destructive/10 border border-destructive/30 p-3 space-y-3">
                            <div className="flex items-start gap-2 text-sm">
                                <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
                                <span className="text-destructive font-medium">
                                    Are you sure? The project files will be deleted from this server.
                                </span>
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    variant="destructive"
                                    size="sm"
                                    disabled={deleting}
                                    onClick={() => void handleDelete()}
                                >
                                    {deleting ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 mr-1.5" />}
                                    Yes, Delete Project
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={deleting}
                                    onClick={() => setConfirmDelete(false)}
                                >
                                    Cancel
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export interface ProjectSettingsTabProps {
    projectId: string;
    user: User | null;
}

export function ProjectSettingsTab({ projectId, user }: ProjectSettingsTabProps) {
    const [subTab, setSubTab] = useState<SubTab>("members");

    return (
        <div className="flex h-full overflow-hidden">
            {/* Sub-nav sidebar */}
            <nav className="w-44 shrink-0 border-r bg-muted/20 p-3 space-y-0.5">
                <button
                    className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors",
                        subTab === "members"
                            ? "bg-secondary text-secondary-foreground font-medium"
                            : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                    )}
                    onClick={() => setSubTab("members")}
                >
                    <Users className="h-4 w-4" /> Members
                </button>
                <button
                    className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors",
                        subTab === "general"
                            ? "bg-secondary text-secondary-foreground font-medium"
                            : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                    )}
                    onClick={() => setSubTab("general")}
                >
                    <Settings2 className="h-4 w-4" /> General
                </button>
            </nav>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
                {subTab === "members" && <MembersSubTab projectId={projectId} user={user} />}
                {subTab === "general" && <GeneralSubTab projectId={projectId} userEmail={user?.email ?? ""} />}
            </div>
        </div>
    );
}

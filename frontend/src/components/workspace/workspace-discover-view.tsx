import { useCallback, useEffect, useState } from "react";
import { Globe, Lock, Users, Loader2, CheckCircle2, Clock, ShieldAlert, Github, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { fetchApi, readApiError } from "@/lib/api";
import type { User } from "@/types/auth";

interface DiscoverProject {
    id: string;
    name: string;
    display_name?: string;
    description?: string;
    visibility: "public" | "private" | "hidden";
    my_role: string | null;
    my_membership_role: string | null;
    pending_request: string | null;
    github_source_url?: string | null;
}

interface GitHubRepo {
    id: number;
    name: string;
    full_name: string;
    description: string;
    clone_url: string;
    html_url: string;
    private: boolean;
    updated_at: string;
    already_cloned: boolean;
}

interface RequestAccessDialogProps {
    project: DiscoverProject;
    onClose: () => void;
    onSuccess: () => void;
}

function RequestAccessDialog({ project, onClose, onSuccess }: RequestAccessDialogProps) {
    const [role, setRole] = useState<"viewer" | "manager">("viewer");
    const [loading, setLoading] = useState(false);

    const submit = async () => {
        setLoading(true);
        try {
            const resp = await fetchApi(`/api/projects/${project.id}/request-access`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ requested_role: role }),
            });
            if (!resp.ok) {
                toast.error(await readApiError(resp, "Request failed"));
                return;
            }
            toast.success("Access request submitted");
            onSuccess();
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-background rounded-lg shadow-xl p-6 w-80 space-y-4">
                <h3 className="font-semibold text-lg">Request Access</h3>
                <p className="text-sm text-muted-foreground">
                    Request access to <strong>{project.display_name || project.name}</strong>
                </p>
                <div className="space-y-2">
                    <p className="text-sm font-medium">Requested role</p>
                    <div className="flex gap-2">
                        <Button
                            variant={role === "viewer" ? "default" : "outline"}
                            size="sm"
                            onClick={() => setRole("viewer")}
                        >
                            Viewer
                        </Button>
                        <Button
                            variant={role === "manager" ? "default" : "outline"}
                            size="sm"
                            onClick={() => setRole("manager")}
                        >
                            Manager
                        </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                        {role === "viewer" ? "Read-only access to view files and comments." : "Can create comments and manage project settings."}
                    </p>
                </div>
                <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
                    <Button onClick={submit} disabled={loading}>
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit Request"}
                    </Button>
                </div>
            </div>
        </div>
    );
}

interface CloneDialogProps {
    repo: GitHubRepo;
    canCreateHidden: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

function CloneDialog({ repo, canCreateHidden, onClose, onSuccess }: CloneDialogProps) {
    const [name, setName] = useState(repo.name);
    const [description, setDescription] = useState(repo.description || "");
    const [visibility, setVisibility] = useState<"public" | "private" | "hidden">("public");
    const [loading, setLoading] = useState(false);

    const submit = async () => {
        setLoading(true);
        try {
            const resp = await fetchApi("/api/github/repos/clone", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    clone_url: repo.clone_url,
                    name,
                    description,
                    visibility,
                }),
            });
            if (!resp.ok) {
                toast.error(await readApiError(resp, "Clone failed"));
                return;
            }
            toast.success(`"${name}" cloned successfully`);
            onSuccess();
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-background rounded-lg shadow-xl p-6 w-96 space-y-4">
                <div className="flex items-center gap-2">
                    <Github className="h-5 w-5" />
                    <h3 className="font-semibold text-lg">Clone Repository</h3>
                </div>
                <p className="text-sm text-muted-foreground">
                    Clone <strong>{repo.full_name}</strong> onto this server as a read-only project.
                </p>
                <div className="space-y-3">
                    <div>
                        <label className="text-sm font-medium block mb-1">Project name</label>
                        <input
                            className="w-full border rounded px-3 py-1.5 text-sm bg-background"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </div>
                    <div>
                        <label className="text-sm font-medium block mb-1">Description</label>
                        <input
                            className="w-full border rounded px-3 py-1.5 text-sm bg-background"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Optional description"
                        />
                    </div>
                    <div>
                        <label className="text-sm font-medium block mb-1">Visibility</label>
                        <div className="flex gap-2">
                            {(["public", "private"] as const).map((v) => (
                                <Button
                                    key={v}
                                    variant={visibility === v ? "default" : "outline"}
                                    size="sm"
                                    onClick={() => setVisibility(v)}
                                >
                                    {v.charAt(0).toUpperCase() + v.slice(1)}
                                </Button>
                            ))}
                            {canCreateHidden && (
                                <Button
                                    variant={visibility === "hidden" ? "default" : "outline"}
                                    size="sm"
                                    onClick={() => setVisibility("hidden")}
                                >
                                    Hidden
                                </Button>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
                    <Button onClick={submit} disabled={loading || !name.trim()}>
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Clone"}
                    </Button>
                </div>
            </div>
        </div>
    );
}

interface WorkspaceDiscoverViewProps {
    user: User | null;
}

export function WorkspaceDiscoverView({ user }: WorkspaceDiscoverViewProps) {
    const [projects, setProjects] = useState<DiscoverProject[]>([]);
    const [loading, setLoading] = useState(true);
    const [requestTarget, setRequestTarget] = useState<DiscoverProject | null>(null);

    // GitHub repos (only loaded for designer+)
    const [githubRepos, setGithubRepos] = useState<GitHubRepo[]>([]);
    const [githubLoading, setGithubLoading] = useState(false);
    const [githubError, setGithubError] = useState<string | null>(null);
    const [cloneTarget, setCloneTarget] = useState<GitHubRepo | null>(null);

    const isDesignerOrAbove = user?.role === "designer" || user?.role === "admin";
    const isAdmin = user?.role === "admin";

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await fetchApi("/api/projects/discover");
            if (resp.ok) {
                setProjects(await resp.json());
            }
        } finally {
            setLoading(false);
        }
    }, []);

    const loadGithubRepos = useCallback(async () => {
        if (!isDesignerOrAbove) return;
        setGithubLoading(true);
        setGithubError(null);
        try {
            const resp = await fetchApi("/api/github/repos");
            if (resp.ok) {
                setGithubRepos(await resp.json());
            } else {
                const msg = await readApiError(resp, "Failed to load GitHub repos");
                setGithubError(msg);
            }
        } catch {
            setGithubError("Could not connect to GitHub API");
        } finally {
            setGithubLoading(false);
        }
    }, [isDesignerOrAbove]);

    useEffect(() => { void load(); }, [load]);
    useEffect(() => { void loadGithubRepos(); }, [loadGithubRepos]);

    if (loading) {
        return (
            <div className="flex h-48 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (projects.length === 0 && (!isDesignerOrAbove || githubRepos.length === 0)) {
        return (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
                <Globe className="h-8 w-8 opacity-30" />
                <p className="text-sm">No discoverable projects found.</p>
            </div>
        );
    }

    const withAccess = projects.filter((p) => p.my_role);
    const pending = projects.filter((p) => !p.my_role && p.pending_request);
    const noAccess = projects.filter((p) => !p.my_role && !p.pending_request);

    const renderProject = (project: DiscoverProject) => {
        const displayName = project.display_name || project.name;
        const hasAccess = !!project.my_role;
        const isPending = !hasAccess && !!project.pending_request;
        const isGitHubSource = !!project.github_source_url;

        return (
            <div
                key={project.id}
                className={cn(
                    "flex flex-col rounded-lg border bg-card transition-colors",
                    hasAccess && "border-green-500/40 bg-green-500/5",
                    isPending && "border-yellow-500/40 bg-yellow-500/5",
                    !hasAccess && !isPending && "border-border opacity-60"
                )}
            >
                {/* Access status strip */}
                <div className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-t-lg border-b",
                    hasAccess && "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20",
                    isPending && "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20",
                    !hasAccess && !isPending && "bg-muted/50 text-muted-foreground border-border"
                )}>
                    {hasAccess && <><CheckCircle2 className="h-3.5 w-3.5" /> You have access — <span className="capitalize">{project.my_role}</span></>}
                    {isPending && <><Clock className="h-3.5 w-3.5" /> Access request pending</>}
                    {!hasAccess && !isPending && <><ShieldAlert className="h-3.5 w-3.5" /> No access</>}
                </div>

                {/* Content */}
                <div className="flex-1 p-4">
                    <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                            {isGitHubSource && (
                                <span title="Cloned from GitHub">
                                    <Github className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                                </span>
                            )}
                            <h3 className="font-semibold text-sm leading-snug truncate">{displayName}</h3>
                        </div>
                        <Badge
                            variant="outline"
                            className={cn(
                                "flex items-center gap-1 text-[10px] shrink-0",
                                project.visibility === "public" && "border-green-500/50 text-green-700 dark:text-green-400",
                                project.visibility === "private" && "border-yellow-500/50 text-yellow-700 dark:text-yellow-400"
                            )}
                        >
                            {project.visibility === "public"
                                ? <><Globe className="h-2.5 w-2.5" /> Public</>
                                : <><Lock className="h-2.5 w-2.5" /> Private</>
                            }
                        </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-2 min-h-[2.5rem]">
                        {project.description || <span className="italic opacity-60">No description provided.</span>}
                    </p>
                </div>

                {/* Action */}
                {!hasAccess && !isPending && user && (
                    <div className="px-4 pb-4">
                        <Button size="sm" variant="outline" className="w-full" onClick={() => setRequestTarget(project)}>
                            <Users className="h-3.5 w-3.5 mr-1.5" />
                            Request to Join
                        </Button>
                    </div>
                )}
            </div>
        );
    };

    const renderGitHubRepo = (repo: GitHubRepo) => (
        <div
            key={repo.id}
            className={cn(
                "flex flex-col rounded-lg border bg-card transition-colors",
                repo.already_cloned ? "border-blue-500/40 bg-blue-500/5 opacity-70" : "border-border"
            )}
        >
            {/* Status strip */}
            <div className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-t-lg border-b",
                repo.already_cloned
                    ? "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20"
                    : "bg-muted/50 text-muted-foreground border-border"
            )}>
                <Github className="h-3.5 w-3.5" />
                {repo.already_cloned ? "Already on server" : "Available to clone"}
            </div>

            {/* Content */}
            <div className="flex-1 p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                        <h3 className="font-semibold text-sm leading-snug truncate">{repo.name}</h3>
                    </div>
                    <Badge
                        variant="outline"
                        className={cn(
                            "flex items-center gap-1 text-[10px] shrink-0",
                            repo.private
                                ? "border-yellow-500/50 text-yellow-700 dark:text-yellow-400"
                                : "border-green-500/50 text-green-700 dark:text-green-400"
                        )}
                    >
                        {repo.private ? <><Lock className="h-2.5 w-2.5" /> Private</> : <><Globe className="h-2.5 w-2.5" /> Public</>}
                    </Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2 min-h-[2.5rem]">
                    {repo.description || <span className="italic opacity-60">No description provided.</span>}
                </p>
            </div>

            {/* Action */}
            {!repo.already_cloned && (
                <div className="px-4 pb-4">
                    <Button size="sm" variant="outline" className="w-full" onClick={() => setCloneTarget(repo)}>
                        <Download className="h-3.5 w-3.5 mr-1.5" />
                        Clone to Server
                    </Button>
                </div>
            )}
        </div>
    );

    return (
        <>
            <div className="mb-6">
                <h2 className="text-lg font-semibold">Discover</h2>
                <p className="text-sm text-muted-foreground mt-0.5">
                    {projects.length} project{projects.length !== 1 ? "s" : ""} on this server
                    {withAccess.length > 0 && ` · ${withAccess.length} accessible`}
                    {noAccess.length > 0 && ` · ${noAccess.length} without access`}
                    {pending.length > 0 && ` · ${pending.length} pending`}
                </p>
            </div>

            {noAccess.length > 0 && (
                <section className="mb-8">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                        Available to Join ({noAccess.length})
                    </h3>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                        {noAccess.map(renderProject)}
                    </div>
                </section>
            )}

            {pending.length > 0 && (
                <section className="mb-8">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                        Pending Requests ({pending.length})
                    </h3>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                        {pending.map(renderProject)}
                    </div>
                </section>
            )}

            {withAccess.length > 0 && (
                <section className="mb-8">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                        Projects You Have Access To ({withAccess.length})
                    </h3>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                        {withAccess.map(renderProject)}
                    </div>
                </section>
            )}

            {/* GitHub Repos section — only visible to designers and admins */}
            {isDesignerOrAbove && (
                <section className="mt-8 border-t pt-8">
                    <div className="flex items-center gap-2 mb-1">
                        <Github className="h-4 w-4" />
                        <h2 className="text-lg font-semibold">GitHub Repositories</h2>
                    </div>
                    <p className="text-sm text-muted-foreground mb-4">
                        Repositories accessible via your GitHub account. Clone any repo to add it as a read-only project on this server.
                    </p>

                    {githubLoading && (
                        <div className="flex h-24 items-center justify-center">
                            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                    )}

                    {!githubLoading && githubError && (
                        <div className="rounded-lg border border-yellow-500/40 bg-yellow-500/5 p-4 text-sm text-yellow-700 dark:text-yellow-400">
                            <p className="font-medium mb-1">Could not load GitHub repositories</p>
                            <p className="text-xs opacity-80">{githubError}</p>
                            <p className="text-xs mt-2 opacity-70">
                                Make sure you are signed in with GitHub or that the server has a GITHUB_TOKEN configured.
                            </p>
                        </div>
                    )}

                    {!githubLoading && !githubError && githubRepos.length === 0 && (
                        <div className="flex h-24 flex-col items-center justify-center gap-1 text-muted-foreground">
                            <Github className="h-6 w-6 opacity-30" />
                            <p className="text-sm">No repositories found.</p>
                        </div>
                    )}

                    {!githubLoading && !githubError && githubRepos.length > 0 && (
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                            {githubRepos.map(renderGitHubRepo)}
                        </div>
                    )}
                </section>
            )}

            {requestTarget && (
                <RequestAccessDialog
                    project={requestTarget}
                    onClose={() => setRequestTarget(null)}
                    onSuccess={() => { setRequestTarget(null); void load(); }}
                />
            )}

            {cloneTarget && (
                <CloneDialog
                    repo={cloneTarget}
                    canCreateHidden={isAdmin}
                    onClose={() => setCloneTarget(null)}
                    onSuccess={() => {
                        setCloneTarget(null);
                        void load();
                        void loadGithubRepos();
                    }}
                />
            )}
        </>
    );
}

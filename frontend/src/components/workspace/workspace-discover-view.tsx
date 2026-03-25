import { useCallback, useEffect, useState } from "react";
import { Globe, Lock, EyeOff, Users, Loader2, Check, Clock, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
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
                    <label className="text-sm font-medium">Requested role</label>
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
                </div>
                <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
                    <Button onClick={submit} disabled={loading}>
                        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit"}
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

    useEffect(() => { void load(); }, [load]);

    const handleJoin = async (project: DiscoverProject) => {
        const resp = await fetchApi(`/api/projects/${project.id}/join`, { method: "POST" });
        if (resp.ok) {
            toast.success(`Joined ${project.display_name || project.name}`);
            void load();
        } else {
            toast.error(await readApiError(resp, "Could not join project"));
        }
    };

    const visibilityIcon = (v: DiscoverProject["visibility"]) => {
        if (v === "public") return <Globe className="h-3 w-3 text-green-500" />;
        if (v === "private") return <Lock className="h-3 w-3 text-yellow-500" />;
        return <EyeOff className="h-3 w-3 text-muted-foreground" />;
    };

    const visibilityLabel = (v: DiscoverProject["visibility"]) => {
        if (v === "public") return "Public";
        if (v === "private") return "Private";
        return "Hidden";
    };

    if (loading) {
        return (
            <div className="flex h-48 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (projects.length === 0) {
        return (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-muted-foreground">
                <Globe className="h-8 w-8 opacity-30" />
                <p className="text-sm">No discoverable projects found.</p>
            </div>
        );
    }

    return (
        <>
            <div className="mb-4">
                <h2 className="text-lg font-semibold">Discover Projects</h2>
                <p className="text-sm text-muted-foreground">Browse public and private projects you can join.</p>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {projects.map((project) => (
                    <Card key={project.id} className="flex flex-col">
                        <CardContent className="flex-1 p-4">
                            <div className="flex items-start justify-between gap-2 mb-1">
                                <h3 className="font-semibold text-base leading-tight truncate">
                                    {project.display_name || project.name}
                                </h3>
                                <Badge variant="outline" className="flex items-center gap-1 text-[10px] shrink-0">
                                    {visibilityIcon(project.visibility)}
                                    {visibilityLabel(project.visibility)}
                                </Badge>
                            </div>
                            {project.description && (
                                <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                                    {project.description}
                                </p>
                            )}
                            {project.my_role && (
                                <div className="mt-2 flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                                    <Check className="h-3 w-3" />
                                    You have access ({project.my_role})
                                </div>
                            )}
                            {project.pending_request && !project.my_role && (
                                <div className="mt-2 flex items-center gap-1 text-xs text-yellow-600 dark:text-yellow-400">
                                    <Clock className="h-3 w-3" />
                                    Access request pending
                                </div>
                            )}
                        </CardContent>
                        <CardFooter className="p-3 pt-0">
                            {!project.my_role && !project.pending_request && user && (
                                <>
                                    {project.visibility === "public" ? (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="w-full"
                                            onClick={() => handleJoin(project)}
                                        >
                                            <LogIn className="h-3.5 w-3.5 mr-1" />
                                            Join
                                        </Button>
                                    ) : (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="w-full"
                                            onClick={() => setRequestTarget(project)}
                                        >
                                            <Users className="h-3.5 w-3.5 mr-1" />
                                            Request Access
                                        </Button>
                                    )}
                                </>
                            )}
                        </CardFooter>
                    </Card>
                ))}
            </div>

            {requestTarget && (
                <RequestAccessDialog
                    project={requestTarget}
                    onClose={() => setRequestTarget(null)}
                    onSuccess={() => { setRequestTarget(null); void load(); }}
                />
            )}
        </>
    );
}

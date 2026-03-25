import { useState } from "react";
import { Project } from "@/types/project";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CalendarDays, Box, Trash2, Globe, Lock, EyeOff, ShieldAlert, Clock, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import React from "react";
import { toast } from "sonner";
import { fetchApi, readApiError } from "@/lib/api";

interface ProjectCardProps {
    project: Project;
    compact?: boolean;
    selected?: boolean;
    onClick?: () => void;
    onDoubleClick?: () => void;
    onDelete?: () => void;
    showDelete?: boolean;
    searchQuery?: string;
    actions?: React.ReactNode;
    hasAccess?: boolean;
}

function VisibilityBadge({ visibility }: { visibility?: "public" | "private" | "hidden" }) {
    if (!visibility || visibility === "public") return null;
    if (visibility === "private") {
        return (
            <Badge variant="outline" className="backdrop-blur-sm bg-background/80 border text-[10px] gap-1">
                <Lock className="h-2.5 w-2.5" /> Private
            </Badge>
        );
    }
    return (
        <Badge variant="outline" className="backdrop-blur-sm bg-background/80 border text-[10px] gap-1">
            <EyeOff className="h-2.5 w-2.5" /> Hidden
        </Badge>
    );
}

function highlightMatch(text: string, query: string): React.ReactNode {
    if (!query || !query.trim()) return text;
    const lowerText = text.toLowerCase();
    const lowerQuery = query.toLowerCase();
    const index = lowerText.indexOf(lowerQuery);
    if (index === -1) return text;
    return (
        <>
            {text.slice(0, index)}
            <mark className="bg-yellow-200 dark:bg-yellow-800 px-0.5 rounded text-inherit">
                {text.slice(index, index + query.length)}
            </mark>
            {text.slice(index + query.length)}
        </>
    );
}

interface RequestAccessDialogProps {
    project: Project;
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

    const displayName = project.display_name || project.name;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
            onClick={(e) => { e.stopPropagation(); onClose(); }}
        >
            <div
                className="bg-background rounded-lg shadow-xl p-6 w-80 space-y-4"
                onClick={(e) => e.stopPropagation()}
            >
                <h3 className="font-semibold text-lg">Request Access</h3>
                <p className="text-sm text-muted-foreground">
                    Request access to <strong>{displayName}</strong>
                </p>
                <div className="space-y-2">
                    <p className="text-sm font-medium">Requested role</p>
                    <div className="flex gap-2">
                        <Button variant={role === "viewer" ? "default" : "outline"} size="sm" onClick={() => setRole("viewer")}>
                            Viewer
                        </Button>
                        <Button variant={role === "manager" ? "default" : "outline"} size="sm" onClick={() => setRole("manager")}>
                            Manager
                        </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                        {role === "viewer"
                            ? "Read-only access to view files and comments."
                            : "Can create comments and manage project settings."
                        }
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

export function ProjectCard({
    project,
    compact,
    selected,
    onClick,
    onDoubleClick,
    onDelete,
    showDelete,
    searchQuery = "",
    actions,
    hasAccess = true,
}: ProjectCardProps) {
    const navigate = useNavigate();
    const [showRequestDialog, setShowRequestDialog] = useState(false);
    const [requestPending, setRequestPending] = useState(false);

    const thumbnailUrl = project.thumbnail_url ?? null;
    const displayName = project.display_name || project.name;
    const description = project.description || "No description available.";
    const parentRepo = project.parent_repo;

    const handleClick = () => {
        if (!hasAccess) return;
        if (onClick) { onClick(); } else { navigate(`/project/${project.id}`); }
    };

    if (compact) {
        return (
            <>
                <Card
                    className={`overflow-hidden transition-all bg-card border shadow-sm ${
                        hasAccess
                            ? "cursor-pointer group " + (selected ? "border-primary shadow-md" : "hover:border-primary/50 hover:shadow-md")
                            : "cursor-default opacity-60"
                    }`}
                    onClick={handleClick}
                    onDoubleClick={hasAccess ? onDoubleClick : undefined}
                >
                    <div className="flex items-center gap-3 p-3">
                        <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center shrink-0 overflow-hidden">
                            {thumbnailUrl ? (
                                <img src={thumbnailUrl} alt={displayName} className="w-full h-full object-cover" />
                            ) : (
                                <Box className="h-6 w-6 opacity-20" />
                            )}
                        </div>
                        <div className="min-w-0 flex-1">
                            <h3 className="font-medium text-sm truncate">{highlightMatch(displayName, searchQuery)}</h3>
                            <p className="text-xs text-muted-foreground">{project.last_modified}</p>
                        </div>
                        {!hasAccess && (
                            <div onClick={(e) => e.stopPropagation()}>
                                {requestPending ? (
                                    <Badge variant="outline" className="text-[10px] gap-1 text-yellow-600 dark:text-yellow-400 border-yellow-500/50">
                                        <Clock className="h-3 w-3" /> Pending
                                    </Badge>
                                ) : (
                                    <Button size="sm" variant="outline" className="h-6 text-[11px] px-2" onClick={() => setShowRequestDialog(true)}>
                                        Request Access
                                    </Button>
                                )}
                            </div>
                        )}
                    </div>
                </Card>
                {showRequestDialog && (
                    <RequestAccessDialog
                        project={project}
                        onClose={() => setShowRequestDialog(false)}
                        onSuccess={() => { setShowRequestDialog(false); setRequestPending(true); }}
                    />
                )}
            </>
        );
    }

    return (
        <>
            <Card
                className={`overflow-hidden transition-all bg-card border shadow-sm ${
                    hasAccess
                        ? "cursor-pointer group " + (selected ? "border-primary shadow-md" : "hover:border-primary/50 hover:shadow-md")
                        : "cursor-default opacity-70"
                }`}
                onClick={handleClick}
                onDoubleClick={hasAccess ? onDoubleClick : undefined}
            >
                <div className="aspect-video w-full overflow-hidden bg-muted relative border-b">
                    {thumbnailUrl ? (
                        <img
                            src={thumbnailUrl}
                            alt={displayName}
                            className={`w-full h-full object-cover ${hasAccess ? "group-hover:scale-105 transition-transform duration-300" : ""}`}
                        />
                    ) : (
                        <div className="flex items-center justify-center h-full text-muted-foreground bg-muted/30">
                            <Box className="h-10 w-10 opacity-20" />
                        </div>
                    )}

                    {!hasAccess && (
                        <div className="absolute inset-0 flex items-center justify-center bg-background/40 backdrop-blur-[2px]">
                            <div className="flex flex-col items-center gap-1 text-muted-foreground">
                                <ShieldAlert className="h-8 w-8 opacity-60" />
                                <span className="text-[11px] font-medium opacity-70">No Access</span>
                            </div>
                        </div>
                    )}

                    <div className="absolute top-2 right-2 flex gap-1">
                        {parentRepo && (
                            <Badge variant="secondary" className="backdrop-blur-sm bg-background/80 border text-[10px]">
                                {highlightMatch(parentRepo, searchQuery)}
                            </Badge>
                        )}
                        <Badge variant="secondary" className="backdrop-blur-sm bg-background/80 border text-[10px]">
                            Git
                        </Badge>
                        <VisibilityBadge visibility={project.visibility} />
                        {actions && hasAccess ? (
                            <div onClick={(event) => event.stopPropagation()} onPointerDown={(event) => event.stopPropagation()}>
                                {actions}
                            </div>
                        ) : null}
                        {showDelete && onDelete && hasAccess && (
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 bg-background/80 backdrop-blur-sm hover:bg-destructive hover:text-destructive-foreground"
                                onClick={(e) => { e.stopPropagation(); onDelete(); }}
                            >
                                <Trash2 className="h-3 w-3" />
                            </Button>
                        )}
                    </div>
                </div>

                <CardContent className="p-4">
                    <h3 className={`font-semibold text-lg tracking-tight mb-1 truncate ${hasAccess ? "group-hover:text-primary transition-colors" : ""}`}>
                        {highlightMatch(displayName, searchQuery)}
                    </h3>
                    <p className="text-sm text-muted-foreground line-clamp-2 min-h-[2.5rem]">
                        {highlightMatch(description, searchQuery)}
                    </p>
                </CardContent>

                <CardFooter className="p-4 pt-0 border-t-0 text-[11px] text-muted-foreground flex items-center gap-2">
                    {hasAccess ? (
                        <>
                            <CalendarDays className="h-3.5 w-3.5" />
                            <span>Updated {project.last_modified}</span>
                            {project.visibility === "public" && (
                                <span className="ml-auto flex items-center gap-1 text-green-600 dark:text-green-400">
                                    <Globe className="h-3 w-3" /> Public
                                </span>
                            )}
                            {project.visibility === "private" && (
                                <span className="ml-auto flex items-center gap-1 text-yellow-600 dark:text-yellow-400">
                                    <Lock className="h-3 w-3" /> Private
                                </span>
                            )}
                            {project.visibility === "hidden" && (
                                <span className="ml-auto flex items-center gap-1 text-muted-foreground">
                                    <EyeOff className="h-3 w-3" /> Hidden
                                </span>
                            )}
                        </>
                    ) : (
                        <div
                            className="w-full"
                            onClick={(e) => e.stopPropagation()}
                            onPointerDown={(e) => e.stopPropagation()}
                        >
                            {requestPending ? (
                                <div className="flex items-center gap-1.5 text-yellow-600 dark:text-yellow-400">
                                    <Clock className="h-3.5 w-3.5" />
                                    <span>Access request pending</span>
                                </div>
                            ) : (
                                <Button
                                    size="sm"
                                    variant="outline"
                                    className="w-full h-7 text-xs"
                                    onClick={() => setShowRequestDialog(true)}
                                >
                                    <ShieldAlert className="h-3.5 w-3.5 mr-1.5" />
                                    Request Access
                                </Button>
                            )}
                        </div>
                    )}
                </CardFooter>
            </Card>

            {showRequestDialog && (
                <RequestAccessDialog
                    project={project}
                    onClose={() => setShowRequestDialog(false)}
                    onSuccess={() => { setShowRequestDialog(false); setRequestPending(true); }}
                />
            )}
        </>
    );
}

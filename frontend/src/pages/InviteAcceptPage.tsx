import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Loader2, CheckCircle2, XCircle, LogIn } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import prismLogoMark from "@/assets/branding/kicad-prism/kicad-prism-icon.svg";

interface InviteInfo {
    id: string;
    project_id: string;
    project_name: string;
    invited_email: string;
    invited_role: string;
    invited_by: string;
    status: string;
    created_at: string;
    expires_at: string | null;
}

const roleBadgeVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    admin: "destructive",
    manager: "default",
    viewer: "secondary",
};

export function InviteAcceptPage() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const token = searchParams.get("token") ?? "";

    const [invite, setInvite] = useState<InviteInfo | null>(null);
    const [isAuthenticatedUser, setIsAuthenticatedUser] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [actionState, setActionState] = useState<"idle" | "accepting" | "declining" | "accepted" | "declined">("idle");

    useEffect(() => {
        if (!token) {
            setError("No invite token provided.");
            setLoading(false);
            return;
        }

        const load = async () => {
            try {
                const [infoRes, meRes] = await Promise.allSettled([
                    fetch(`/api/projects/invite/info?token=${encodeURIComponent(token)}`),
                    fetch("/api/auth/me"),
                ]);

                if (infoRes.status === "fulfilled") {
                    if (!infoRes.value.ok) {
                        const payload = await infoRes.value.json().catch(() => ({}));
                        throw new Error((payload as any).detail || "Invite not found or has expired.");
                    }
                    setInvite(await infoRes.value.json());
                } else {
                    throw new Error("Failed to load invite information.");
                }

                if (meRes.status === "fulfilled" && meRes.value.ok) {
                    setIsAuthenticatedUser(true);
                }
            } catch (err: any) {
                setError(err.message || "Failed to load invite.");
            } finally {
                setLoading(false);
            }
        };

        void load();
    }, [token]);

    const handleAccept = async () => {
        if (!invite) return;
        setActionState("accepting");
        try {
            const res = await fetch("/api/projects/invite/accept", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token }),
            });
            if (!res.ok) {
                const payload = await res.json().catch(() => ({}));
                setError((payload as any).detail || "Failed to accept invite.");
                setActionState("idle");
                return;
            }
            setActionState("accepted");
        } catch {
            setError("Network error. Please try again.");
            setActionState("idle");
        }
    };

    const handleDecline = async () => {
        if (!invite) return;
        setActionState("declining");
        try {
            const res = await fetch(`/api/projects/invites/${invite.id}/decline`, {
                method: "POST",
            });
            if (!res.ok) {
                const payload = await res.json().catch(() => ({}));
                setError((payload as any).detail || "Failed to decline invite.");
                setActionState("idle");
                return;
            }
            setActionState("declined");
        } catch {
            setError("Network error. Please try again.");
            setActionState("idle");
        }
    };

    const handleSignIn = () => {
        const returnTo = encodeURIComponent(window.location.pathname + window.location.search);
        navigate(`/?next=${returnTo}`);
    };

    return (
        <div className="flex min-h-screen items-center justify-center bg-background px-4">
            <div className="w-full max-w-sm space-y-6">
                <div className="flex items-center justify-center gap-2">
                    <img src={prismLogoMark} alt="KiCAD Prism" className="h-8 w-8" />
                    <span className="text-xl font-semibold tracking-tight">KiCAD Prism</span>
                </div>

                <Card className="border-primary/40 ring-1 ring-primary/30">
                    <CardHeader className="space-y-1 pb-4">
                        <CardTitle className="text-xl">Project Invitation</CardTitle>
                        <CardDescription>
                            {loading ? "Loading invite details…" : invite ? `You've been invited to join a project` : "Invite details"}
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {loading && (
                            <div className="flex items-center justify-center py-6">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        )}

                        {!loading && error && actionState === "idle" && (
                            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                                {error}
                            </div>
                        )}

                        {!loading && invite && actionState === "idle" && (
                            <>
                                <div className="space-y-3 rounded-md bg-muted/40 p-3 text-sm">
                                    <div className="flex items-center justify-between">
                                        <span className="text-muted-foreground">Project</span>
                                        <span className="font-medium">{invite.project_name}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-muted-foreground">Invited as</span>
                                        <Badge variant={roleBadgeVariant[invite.invited_role] ?? "secondary"} className="capitalize">
                                            {invite.invited_role}
                                        </Badge>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-muted-foreground">Invited by</span>
                                        <span className="font-medium">{invite.invited_by}</span>
                                    </div>
                                    {invite.expires_at && (
                                        <div className="flex items-center justify-between">
                                            <span className="text-muted-foreground">Expires</span>
                                            <span className="text-xs text-muted-foreground">
                                                {new Date(invite.expires_at).toLocaleDateString()}
                                            </span>
                                        </div>
                                    )}
                                </div>

                                {invite.status !== "pending" && (
                                    <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground text-center">
                                        This invite has already been <strong>{invite.status}</strong>.
                                    </div>
                                )}

                                {invite.status === "pending" && isAuthenticatedUser && (
                                    <div className="flex gap-2">
                                        <Button className="flex-1" onClick={handleAccept}>
                                            Accept Invite
                                        </Button>
                                        <Button variant="outline" className="flex-1" onClick={handleDecline}>
                                            Decline
                                        </Button>
                                    </div>
                                )}

                                {invite.status === "pending" && !isAuthenticatedUser && (
                                    <div className="space-y-3">
                                        <p className="text-sm text-muted-foreground text-center">
                                            Sign in to accept this invitation.
                                        </p>
                                        <Button className="w-full" onClick={handleSignIn}>
                                            <LogIn className="mr-2 h-4 w-4" />
                                            Sign In
                                        </Button>
                                    </div>
                                )}
                            </>
                        )}

                        {actionState === "accepting" && (
                            <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Accepting invite…
                            </div>
                        )}

                        {actionState === "accepted" && (
                            <div className="space-y-4">
                                <div className="flex flex-col items-center gap-2 py-2 text-center">
                                    <CheckCircle2 className="h-8 w-8 text-green-500" />
                                    <p className="font-medium">Invite accepted!</p>
                                    <p className="text-sm text-muted-foreground">
                                        You now have access to <strong>{invite?.project_name}</strong>.
                                    </p>
                                </div>
                                <Button className="w-full" onClick={() => navigate(`/project/${invite?.project_id}`)}>
                                    Open Project
                                </Button>
                            </div>
                        )}

                        {actionState === "declining" && (
                            <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Declining invite…
                            </div>
                        )}

                        {actionState === "declined" && (
                            <div className="flex flex-col items-center gap-2 py-2 text-center">
                                <XCircle className="h-8 w-8 text-muted-foreground" />
                                <p className="font-medium">Invite declined</p>
                                <p className="text-sm text-muted-foreground">
                                    You have declined the invitation to <strong>{invite?.project_name}</strong>.
                                </p>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

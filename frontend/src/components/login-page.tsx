import { GoogleLogin, GoogleOAuthProvider, type CredentialResponse } from "@react-oauth/google";
import { useEffect, useState } from "react";
import { Binary, Loader2 } from "lucide-react";

import prismLogoHorizontal from "@/assets/branding/kicad-prism/kicad-prism-logo-horizontal.svg";
import prismLogoMark from "@/assets/branding/kicad-prism/kicad-prism-icon.svg";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { User } from "@/types/auth";

interface LoginPageProps {
  onLoginSuccess: (user: User) => void;
  googleClientId: string;
  devMode?: boolean;
  workspaceName?: string;
  initialError?: string | null;
}

const RELEASE_CACHE_KEY = "kicad_prism_latest_release_tag";
const RELEASE_CACHE_TIME_KEY = "kicad_prism_latest_release_tag_fetched_at";
const RELEASE_CACHE_TTL_MS = 15 * 60 * 1000;
const DEFAULT_GITHUB_REPO = "krishna-swaroop/KiCAD-Prism";

export function LoginPage({
  onLoginSuccess,
  googleClientId,
  devMode = false,
  workspaceName = "KiCAD Prism",
  initialError = null,
}: LoginPageProps) {
  const [error, setError] = useState<string | null>(initialError);
  const [isLoading, setIsLoading] = useState(false);
  const [releaseTag, setReleaseTag] = useState("...");
  const hostname = typeof window === "undefined" ? "" : window.location.hostname;
  const isLocalOrigin = hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
  const enableOneTap = typeof window !== "undefined" && window.isSecureContext && !isLocalOrigin;

  useEffect(() => {
    setError(initialError);
  }, [initialError]);

  useEffect(() => {
    const cachedTag = window.sessionStorage.getItem(RELEASE_CACHE_KEY);
    const cachedFetchedAt = window.sessionStorage.getItem(RELEASE_CACHE_TIME_KEY);
    if (cachedTag && cachedFetchedAt) {
      const fetchedAt = Number(cachedFetchedAt);
      if (Number.isFinite(fetchedAt) && Date.now() - fetchedAt < RELEASE_CACHE_TTL_MS) {
        setReleaseTag(cachedTag);
        return;
      }
    }

    const controller = new AbortController();
    const repo = import.meta.env.VITE_GITHUB_REPO || DEFAULT_GITHUB_REPO;

    const loadLatestRelease = async () => {
      try {
        const response = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
          headers: {
            Accept: "application/vnd.github+json",
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error("Failed to load release metadata");
        }

        const payload = (await response.json()) as { tag_name?: string; name?: string };
        const tag = payload.tag_name || payload.name || "Unavailable";
        setReleaseTag(tag);
        window.sessionStorage.setItem(RELEASE_CACHE_KEY, tag);
        window.sessionStorage.setItem(RELEASE_CACHE_TIME_KEY, String(Date.now()));
      } catch {
        if (!controller.signal.aborted) {
          setReleaseTag("Unavailable");
        }
      }
    };

    void loadLatestRelease();

    return () => {
      controller.abort();
    };
  }, []);

  const handleSuccess = async (credentialResponse: CredentialResponse) => {
    try {
      setIsLoading(true);
      setError(null);

      if (!credentialResponse.credential) {
        setError("No credentials received from Google");
        return;
      }

      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token: credentialResponse.credential }),
      });

      if (!response.ok) {
        const errorPayload = await response.json();
        throw new Error(errorPayload.detail || "Login failed");
      }

      const user = await response.json();
      onLoginSuccess(user);
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDevBypass = () => {
    window.history.replaceState(null, "", "/");
    onLoginSuccess({ name: "Dev User", email: "dev@pixxel.co.in", role: "admin" });
  };

  return (
    <GoogleOAuthProvider clientId={googleClientId}>
      <div className="grid min-h-screen bg-background text-foreground lg:grid-cols-[minmax(0,1.15fr)_minmax(420px,560px)]">
        <section className="relative hidden border-r bg-card lg:flex lg:flex-col lg:justify-between lg:p-10">
          <div className="relative z-10 flex items-center gap-3">
            <img src={prismLogoHorizontal} alt="KiCAD Prism" className="h-10 w-auto" />
          </div>

          <div className="relative z-10 max-w-xl space-y-6">
            <div className="space-y-3">
              <p className="text-sm font-medium uppercase tracking-[0.22em] text-primary">{workspaceName}</p>
              <h1 className="text-5xl font-semibold tracking-tight">Visualizing KiCAD Projects.</h1>
              <p className="max-w-lg text-base text-muted-foreground">
                A web-based platform for viewing, reviewing, and collaborating on KiCAD projects.
              </p>
            </div>
          </div>

          <div className="relative z-10 flex items-center gap-3 text-xs text-muted-foreground">
            <Binary className="h-3.5 w-3.5" />
            <span>Release {releaseTag}</span>
          </div>
        </section>

        <section className="relative flex items-center justify-center px-6 py-8 sm:px-10">
          <div className="w-full max-w-xl space-y-6 rounded-2xl border border-border/70 bg-card/70 p-5 backdrop-blur-sm sm:p-7">
            <div className="flex items-center justify-center gap-3 lg:hidden">
              <img src={prismLogoMark} alt="KiCAD Prism" className="h-10 w-10" />
              <p className="text-2xl font-semibold tracking-tight">{workspaceName}</p>
            </div>

            <Card className="relative overflow-hidden border-primary/40 bg-card ring-1 ring-primary/30">
              <div className="pointer-events-none absolute inset-0 ring-1 ring-inset ring-border/80" />
              <CardHeader className="space-y-2 pb-7">
                <CardTitle className="text-2xl">Sign In</CardTitle>
                <CardDescription>Sign in with your Google account.</CardDescription>
              </CardHeader>

              <CardContent className="space-y-5 pb-7">
                <div className="flex justify-center">
                  <GoogleLogin
                    onSuccess={handleSuccess}
                    onError={() => setError("Google sign-in failed")}
                    useOneTap={enableOneTap}
                    auto_select={enableOneTap}
                    theme="outline"
                    shape="pill"
                    size="large"
                    width="100%"
                  />
                </div>

                {isLoading && (
                  <div className="flex items-center justify-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Authenticating…</span>
                  </div>
                )}

                {error && (
                  <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {error}
                  </div>
                )}

                {devMode && (
                  <Button variant="outline" className="w-full" onClick={handleDevBypass}>
                    <Binary className="mr-2 h-4 w-4" />
                    Skip Authentication (Dev Mode)
                  </Button>
                )}
              </CardContent>
            </Card>

            <p className="text-center text-xs text-muted-foreground">
              Restricted Access  |  Contact your administrator for access.
            </p>
          </div>
        </section>
      </div>
    </GoogleOAuthProvider>
  );
}

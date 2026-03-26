import { GoogleLogin, GoogleOAuthProvider, type CredentialResponse } from "@react-oauth/google";
import { useEffect, useState } from "react";
import { Binary, Github, Loader2, Mail } from "lucide-react";
import { Tabs as TabsPrimitive } from "radix-ui";

import prismLogoHorizontal from "@/assets/branding/kicad-prism/kicad-prism-logo-horizontal.svg";
import prismLogoMark from "@/assets/branding/kicad-prism/kicad-prism-icon.svg";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { User } from "@/types/auth";

interface LoginPageProps {
  onLoginSuccess: (user: User) => void;
  googleClientId: string;
  githubClientId?: string;
  providers?: string[];
  devMode?: boolean;
  workspaceName?: string;
  initialError?: string | null;
}

const RELEASE_CACHE_KEY = "kicad_prism_latest_release_tag";
const RELEASE_CACHE_TIME_KEY = "kicad_prism_latest_release_tag_fetched_at";
const RELEASE_CACHE_TTL_MS = 15 * 60 * 1000;
const DEFAULT_GITHUB_REPO = "krishna-swaroop/KiCAD-Prism";

type EmailView = "signin" | "signup" | "forgot";

export function LoginPage({
  onLoginSuccess,
  googleClientId,
  githubClientId = "",
  providers = [],
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

  // Email form state
  const [emailView, setEmailView] = useState<EmailView>("signin");
  const [emailValue, setEmailValue] = useState("");
  const [passwordValue, setPasswordValue] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  // Track OAuth (Google/GitHub) loading separately from email form loading
  const [isOAuthLoading, setIsOAuthLoading] = useState(false);

  // Determine default tab from available providers
  const hasGoogle = providers.includes("google") && googleClientId;
  const hasGitHub = providers.includes("github") && githubClientId;
  const hasEmail = providers.includes("email");
  const defaultTab = hasGoogle ? "google" : hasGitHub ? "github" : "email";

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

  const handleGoogleSuccess = async (credentialResponse: CredentialResponse) => {
    try {
      setIsOAuthLoading(true);
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
      setIsOAuthLoading(false);
    }
  };

  const handleGitHubSignIn = async () => {
    // fastapi-users v13+ returns JSON {authorization_url: "..."} — fetch it
    // then redirect the browser to GitHub for authorization.
    const redirectUrl = encodeURIComponent(window.location.origin + "/");
    try {
      const res = await fetch(`/api/auth/github/authorize?redirect_url=${redirectUrl}`);
      const data = await res.json();
      window.location.href = data.authorization_url;
    } catch {
      setError("Failed to start GitHub sign-in. Please try again.");
    }
  };

  const handleEmailSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsLoading(true);
      setError(null);

      // fastapi-users login expects OAuth2 form-encoded body, not JSON
      const formData = new URLSearchParams();
      formData.append("username", emailValue);
      formData.append("password", passwordValue);

      const response = await fetch("/api/auth/email/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        credentials: "include",
        body: formData.toString(),
      });

      if (!response.ok) {
        const errorPayload = await response.json();
        const detail = errorPayload.detail;
        const message = Array.isArray(detail)
          ? detail.map((e: any) => e.msg ?? String(e)).join("; ")
          : detail || "Sign in failed";
        throw new Error(message);
      }

      // After login, fetch current user session
      const meResponse = await fetch("/api/auth/me", {
        credentials: "include",
      });

      if (!meResponse.ok) {
        if (meResponse.status === 403) {
          const payload = await meResponse.json().catch(() => null) as { detail?: string } | null;
          throw new Error(
            payload?.detail ||
            "Your account is pending admin approval. You will be notified when access is granted."
          );
        }
        throw new Error("Failed to retrieve session after login");
      }

      const user = await meResponse.json();
      onLoginSuccess(user);
    } catch (err: any) {
      setError(err.message || "Sign in failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleEmailSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsLoading(true);
      setError(null);

      const response = await fetch("/api/auth/email/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email: emailValue, password: passwordValue }),
      });

      if (!response.ok) {
        const errorPayload = await response.json();
        throw new Error(errorPayload.detail || "Registration failed");
      }

      setSuccessMessage(
        "Account created. Please check your email to verify your address before signing in."
      );
      setEmailView("signin");
    } catch (err: any) {
      setError(err.message || "Registration failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsLoading(true);
      setError(null);

      await fetch("/api/auth/email/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: emailValue }),
      });

      // Always show success to avoid leaking whether the email exists
      setSuccessMessage("If that address is registered, you'll receive a password reset link shortly.");
      setEmailView("signin");
    } catch {
      setSuccessMessage("If that address is registered, you'll receive a password reset link shortly.");
      setEmailView("signin");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDevBypass = () => {
    window.history.replaceState(null, "", "/");
    onLoginSuccess({ name: "Dev User", email: "dev@pixxel.co.in", role: "admin" });
  };

  const clearMessages = () => {
    setError(null);
    setSuccessMessage(null);
  };

  const showTabs = (hasGoogle ? 1 : 0) + (hasGitHub ? 1 : 0) + (hasEmail ? 1 : 0) > 1;

  const emailFormContent = (
    <div className="space-y-4">
      {emailView === "signin" && (
        <form onSubmit={handleEmailSignIn} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="email-input">Email</Label>
            <Input
              id="email-input"
              type="email"
              placeholder="you@example.com"
              value={emailValue}
              onChange={(e) => setEmailValue(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="password-input">Password</Label>
              <button
                type="button"
                className="text-xs text-primary hover:underline"
                onClick={() => { clearMessages(); setEmailView("forgot"); }}
              >
                Forgot password?
              </button>
            </div>
            <Input
              id="password-input"
              type="password"
              placeholder="••••••••"
              value={passwordValue}
              onChange={(e) => setPasswordValue(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Sign in
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Don't have an account?{" "}
            <button
              type="button"
              className="text-primary hover:underline"
              onClick={() => { clearMessages(); setEmailView("signup"); }}
            >
              Create account
            </button>
          </p>
        </form>
      )}

      {emailView === "signup" && (
        <form onSubmit={handleEmailSignUp} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="signup-email-input">Email</Label>
            <Input
              id="signup-email-input"
              type="email"
              placeholder="you@example.com"
              value={emailValue}
              onChange={(e) => setEmailValue(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="signup-password-input">Password</Label>
            <Input
              id="signup-password-input"
              type="password"
              placeholder="••••••••"
              value={passwordValue}
              onChange={(e) => setPasswordValue(e.target.value)}
              required
              autoComplete="new-password"
            />
          </div>
          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Create account
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Already have an account?{" "}
            <button
              type="button"
              className="text-primary hover:underline"
              onClick={() => { clearMessages(); setEmailView("signin"); }}
            >
              Sign in
            </button>
          </p>
        </form>
      )}

      {emailView === "forgot" && (
        <form onSubmit={handleForgotPassword} className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Enter your email and we'll send you a link to reset your password.
          </p>
          <div className="space-y-1.5">
            <Label htmlFor="forgot-email-input">Email</Label>
            <Input
              id="forgot-email-input"
              type="email"
              placeholder="you@example.com"
              value={emailValue}
              onChange={(e) => setEmailValue(e.target.value)}
              required
              autoComplete="email"
            />
          </div>
          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Send reset link
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            <button
              type="button"
              className="text-primary hover:underline"
              onClick={() => { clearMessages(); setEmailView("signin"); }}
            >
              Back to sign in
            </button>
          </p>
        </form>
      )}
    </div>
  );

  return (
    <GoogleOAuthProvider clientId={googleClientId || "placeholder"}>
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
              <CardHeader className="space-y-2 pb-5">
                <CardTitle className="text-2xl">Sign In</CardTitle>
                <CardDescription>
                  {showTabs
                    ? "Choose how you'd like to sign in."
                    : hasGoogle
                    ? "Sign in with your Google account."
                    : hasGitHub
                    ? "Sign in with your GitHub account."
                    : "Sign in with your email and password."}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-5 pb-7">
                {showTabs ? (
                  <TabsPrimitive.Root defaultValue={defaultTab} onValueChange={clearMessages}>
                    <TabsPrimitive.List className="mb-5 flex rounded-lg border border-border/60 bg-muted/40 p-1 gap-1">
                      {hasGoogle && (
                        <TabsPrimitive.Trigger
                          value="google"
                          className="flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                        >
                          <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
                            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                          </svg>
                          Google
                        </TabsPrimitive.Trigger>
                      )}
                      {hasGitHub && (
                        <TabsPrimitive.Trigger
                          value="github"
                          className="flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                        >
                          <Github className="h-4 w-4" />
                          GitHub
                        </TabsPrimitive.Trigger>
                      )}
                      {hasEmail && (
                        <TabsPrimitive.Trigger
                          value="email"
                          className="flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
                        >
                          <Mail className="h-4 w-4" />
                          Email
                        </TabsPrimitive.Trigger>
                      )}
                    </TabsPrimitive.List>

                    {hasGoogle && (
                      <TabsPrimitive.Content value="google" className="space-y-4">
                        <div className="flex justify-center">
                          <GoogleLogin
                            onSuccess={handleGoogleSuccess}
                            onError={() => setError("Google sign-in failed")}
                            useOneTap={enableOneTap}
                            auto_select={enableOneTap}
                            theme="outline"
                            shape="pill"
                            size="large"
                            width="100%"
                          />
                        </div>
                      </TabsPrimitive.Content>
                    )}

                    {hasGitHub && (
                      <TabsPrimitive.Content value="github" className="space-y-4">
                        <Button
                          className="w-full bg-[#1a7fdc] text-white hover:bg-[#1669b8]"
                          onClick={handleGitHubSignIn}
                          disabled={isLoading}
                        >
                          <Github className="mr-2 h-4 w-4" />
                          Continue with GitHub
                        </Button>
                      </TabsPrimitive.Content>
                    )}

                    {hasEmail && (
                      <TabsPrimitive.Content value="email">
                        {emailFormContent}
                      </TabsPrimitive.Content>
                    )}
                  </TabsPrimitive.Root>
                ) : (
                  <>
                    {hasGoogle && (
                      <div className="flex justify-center">
                        <GoogleLogin
                          onSuccess={handleGoogleSuccess}
                          onError={() => setError("Google sign-in failed")}
                          useOneTap={enableOneTap}
                          auto_select={enableOneTap}
                          theme="outline"
                          shape="pill"
                          size="large"
                          width="100%"
                        />
                      </div>
                    )}
                    {hasGitHub && (
                      <Button
                        className="w-full bg-[#1a7fdc] text-white hover:bg-[#1669b8]"
                        onClick={handleGitHubSignIn}
                        disabled={isLoading}
                      >
                        <Github className="mr-2 h-4 w-4" />
                        Continue with GitHub
                      </Button>
                    )}
                    {hasEmail && emailFormContent}
                  </>
                )}

                {isOAuthLoading && (
                  <div className="flex items-center justify-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Authenticating…</span>
                  </div>
                )}

                {successMessage && (                  <div className="rounded-md border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-700 dark:text-green-400">
                    {successMessage}
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

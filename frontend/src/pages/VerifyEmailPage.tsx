import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import prismLogoMark from "@/assets/branding/kicad-prism/kicad-prism-icon.svg";

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("Invalid or missing verification token.");
      setIsLoading(false);
      return;
    }

    const verify = async () => {
      try {
        const response = await fetch("/api/auth/email/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });

        if (!response.ok) {
          const payload = await response.json();
          throw new Error(payload.detail || "Verification failed.");
        }

        setSuccess(true);
      } catch (err: any) {
        setError(err.message || "Verification failed.");
      } finally {
        setIsLoading(false);
      }
    };

    void verify();
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-center gap-2">
          <img src={prismLogoMark} alt="KiCAD Prism" className="h-8 w-8" />
          <span className="text-xl font-semibold tracking-tight">KiCAD Prism</span>
        </div>

        <Card className="border-primary/40 ring-1 ring-primary/30">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="text-xl">Email Verification</CardTitle>
            <CardDescription>Verifying your email address…</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {isLoading && (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Verifying…</span>
              </div>
            )}

            {!isLoading && success && (
              <>
                <div className="rounded-md border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-700 dark:text-green-400">
                  Your email has been verified. You can now sign in.
                </div>
                <Button className="w-full" onClick={() => { window.location.href = "/"; }}>
                  Go to sign in
                </Button>
              </>
            )}

            {!isLoading && error && (
              <>
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
                <Button variant="outline" className="w-full" onClick={() => { window.location.href = "/"; }}>
                  Go to sign in
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

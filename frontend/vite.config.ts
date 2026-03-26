import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Build the list of hosts Vite's dev server will accept.
// - The hostname from VITE_APP_URL is added automatically.
// - VITE_ALLOWED_HOSTS accepts extra comma-separated hostnames.
function buildAllowedHosts(): string[] | true {
  const hosts: string[] = []
  if (process.env.VITE_APP_URL) {
    try {
      hosts.push(new URL(process.env.VITE_APP_URL).hostname)
    } catch { /* invalid URL — skip */ }
  }
  if (process.env.VITE_ALLOWED_HOSTS) {
    hosts.push(
      ...process.env.VITE_ALLOWED_HOSTS.split(",").map((h) => h.trim()).filter(Boolean)
    )
  }
  // If no custom hosts configured, fall back to Vite's default behaviour.
  return hosts.length > 0 ? hosts : true
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Bind on all interfaces so the dev server is reachable from other
    // devices on the local network (e.g. by IP address).
    host: "0.0.0.0",
    // Allow the app's public hostname without editing this file.
    // Set VITE_APP_URL (and optionally VITE_ALLOWED_HOSTS) in frontend/.env.
    allowedHosts: buildAllowedHosts(),
    proxy: {
      "/api": {
        // Always proxy to localhost — the backend is on the same machine.
        // Set VITE_API_URL for a full URL override, or VITE_BACKEND_PORT to
        // change only the port (defaults to 8000).
        target: process.env.VITE_API_URL ?? `http://127.0.0.1:${process.env.VITE_BACKEND_PORT ?? 8000}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("node_modules/react/") ||
            id.includes("node_modules/react-dom/") ||
            id.includes("node_modules/react-router") ||
            id.includes("node_modules/scheduler/")
          ) {
            return "framework"
          }
          if (
            id.includes("node_modules/react-markdown") ||
            id.includes("node_modules/remark-gfm") ||
            id.includes("node_modules/rehype-raw") ||
            id.includes("node_modules/github-markdown-css")
          ) {
            return "markdown-runtime"
          }
          if (id.includes("node_modules/@react-oauth/google")) {
            return "auth-runtime"
          }
          if (
            id.includes("node_modules/@radix-ui/") ||
            id.includes("node_modules/radix-ui/") ||
            id.includes("node_modules/@base-ui/") ||
            id.includes("node_modules/sonner")
          ) {
            return "ui-runtime"
          }
          if (id.includes("node_modules/lucide-react")) {
            return "icons-runtime"
          }
          if (id.includes("node_modules/online-3d-viewer")) {
            return "viewer3d-runtime"
          }
          if (id.includes("node_modules/three")) {
            return "three-runtime"
          }
          if (id.includes("node_modules")) {
            return "vendor"
          }
        },
      },
    },
  },
})

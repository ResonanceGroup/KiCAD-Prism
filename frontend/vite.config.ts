import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

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
    proxy: {
      "/api": {
        // Always proxy to localhost — the backend is on the same machine.
        target: process.env.VITE_API_URL ?? "http://127.0.0.1:8000",
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

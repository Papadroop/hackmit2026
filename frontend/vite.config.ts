import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    // 5173 is taken by another project on the dev machine.
    port: 5174,
    // The API lives in backend/ (uvicorn on 8400). Proxying keeps it same-origin in dev,
    // so there is no CORS and EventSource works unchanged.
    proxy: {
      "/api": { target: "http://127.0.0.1:8400" },
    },
  },
})

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const staticSecurityHeaders = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4173,
    headers: staticSecurityHeaders,
    proxy: {
      "/api": "http://127.0.0.1:8787",
      "/uploads": "http://127.0.0.1:8787",
    },
  },
  preview: {
    headers: staticSecurityHeaders,
  },
});

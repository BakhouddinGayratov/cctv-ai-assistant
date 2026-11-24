import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const backend = "http://127.0.0.1:8090";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": backend, "/media": backend, "/clips": backend },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 700,
  },
});

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  build: {
    emptyOutDir: true,
    outDir: "dist",
    sourcemap: false,
  },
  plugins: [react()],
  resolve: {
    preserveSymlinks: true,
  },
});

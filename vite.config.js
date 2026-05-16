import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: './' so production builds load assets from file:// inside Electron.
export default defineConfig({
  plugins: [react()],
  base: "./",
});

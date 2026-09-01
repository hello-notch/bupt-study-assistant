import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { localWebApi } from "./dev-api";

export default defineConfig({
  plugins: [vue(), localWebApi()],
  server: {
    port: 5173,
    strictPort: true,
  },
});

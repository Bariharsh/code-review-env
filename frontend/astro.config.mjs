import { defineConfig } from "astro/config";
import svelte from "@astrojs/svelte";

export default defineConfig({
  integrations: [svelte()],
  vite: {
    server: {
      proxy: {
        "/api": "http://127.0.0.1:8000",
      },
    },
  },
});

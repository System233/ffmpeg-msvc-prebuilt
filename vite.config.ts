import { defineConfig } from "vite";
import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { base, siteUrl, repo } from "./scripts/site-config";
export default defineConfig({
  base,
  define: {
    "import.meta.env.VITE_SITE_URL": JSON.stringify(siteUrl),
    "import.meta.env.VITE_GITHUB_REPO_URL": JSON.stringify(repo),
  },
  plugins: [tailwindcss(), reactRouter()],
});

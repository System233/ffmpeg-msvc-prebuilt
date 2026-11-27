const parts = (process.env.BASE_URL ?? "/").split("/").filter(Boolean);
export const base = parts.length ? "/" + parts.join("/") + "/" : "/";
export const repo = (
  process.env.VITE_GITHUB_REPO_URL ??
  "https://github.com/System233/ffmpeg-msvc-prebuilt"
).replace(/\/+$/, "");
export const siteUrl = (
  process.env.VITE_SITE_URL ?? "https://system233.github.io" + base
).replace(/\/+$/, "");

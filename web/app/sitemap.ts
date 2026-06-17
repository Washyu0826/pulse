import type { MetadataRoute } from "next";

import { THEME_ORDER } from "@/components/theme-meta";
import { SITE } from "@/lib/site";

/** 網站地圖：靜態頁 + 5 個主題列表頁 + 6 個模型詳情頁。 */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const staticRoutes = ["", "/dashboard", "/favorites", "/decide", "/newsletter"].map((path) => ({
    url: `${SITE.url}${path}`,
    lastModified: now,
    changeFrequency: "daily" as const,
    priority: path === "" ? 1 : 0.6,
  }));
  const themeRoutes = THEME_ORDER.map((label) => ({
    url: `${SITE.url}/theme/${encodeURIComponent(label)}`,
    lastModified: now,
    changeFrequency: "daily" as const,
    priority: 0.8,
  }));
  const modelRoutes = SITE.models.map((slug) => ({
    url: `${SITE.url}/models/${slug}`,
    lastModified: now,
    changeFrequency: "daily" as const,
    priority: 0.7,
  }));
  return [...staticRoutes, ...themeRoutes, ...modelRoutes];
}

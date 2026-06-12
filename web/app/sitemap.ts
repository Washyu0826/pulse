import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

/** 網站地圖：靜態頁 + 6 個模型詳情頁。 */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const staticRoutes = ["", "/favorites", "/decide"].map((path) => ({
    url: `${SITE.url}${path}`,
    lastModified: now,
    changeFrequency: "daily" as const,
    priority: path === "" ? 1 : 0.6,
  }));
  const modelRoutes = SITE.models.map((slug) => ({
    url: `${SITE.url}/models/${slug}`,
    lastModified: now,
    changeFrequency: "daily" as const,
    priority: 0.7,
  }));
  return [...staticRoutes, ...modelRoutes];
}

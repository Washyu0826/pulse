import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

/** PWA manifest：可「加到主畫面」安裝。圖示沿用 app/icon.svg。 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE.title,
    short_name: SITE.name,
    description: SITE.description,
    start_url: "/",
    display: "standalone",
    background_color: "#F4F7FC",
    theme_color: "#4D74EA",
    lang: "zh-TW",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}

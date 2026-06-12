import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

/** 爬蟲規則：全站可索引，指向 sitemap。 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${SITE.url}/sitemap.xml`,
    host: SITE.url,
  };
}

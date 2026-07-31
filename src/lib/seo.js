export const SITE_URL = "https://assamflood.org";
export const SITE_NAME = "Axom Flood";
export const SOCIAL_IMAGE = `${SITE_URL}/social-card.jpg`;

const INDEXABLE = {
  landing: {
    title: "Assam Flood Information, River Levels and Alerts | Axom Flood",
    description:
      "Check Assam flood alerts, official river measurements, relief camp information and emergency contacts in plain language.",
    path: "/",
  },
  home: {
    title: "Assam Flood Alerts and River Levels | Axom Flood",
    description:
      "Check current Assam river levels, flood alerts, trends and official CWC measurements by village, revenue circle or district.",
    path: "/home/",
  },
  camps: {
    title: "Assam Flood Relief Camps and Shelters | Axom Flood",
    description:
      "Find Assam flood relief camp listings from published district documents. Check each listing with local authorities before travelling.",
    path: "/camps/",
  },
  situation: {
    title: "Assam Flood Impact Situation Report | Axom Flood",
    description:
      "Read validated ASDMA flood impact figures for Assam by district and revenue circle, with report age, source revision and clear limits.",
    path: "/situation/",
  },
  emergency: {
    title: "Assam Flood Emergency Contacts and Helplines | Axom Flood",
    description:
      "Open reviewed Assam flood emergency contacts and helplines, with clear coverage limits and offline access.",
    path: "/emergency/",
  },
};

const NON_INDEXABLE = {
  report: {
    title: "Report Local Flood Conditions in Assam | Axom Flood",
    description:
      "Share local flood conditions without changing the official Assam river status shown by Axom Flood.",
    path: "/report/",
  },
  settings: {
    title: "Settings | Axom Flood",
    description: "Choose location, language, display and notification settings for Axom Flood.",
    path: "/settings/",
  },
};

export function routeKey(pathname) {
  return pathname.split("/").filter(Boolean)[0] || "landing";
}

export function metadataForPath(pathname) {
  const key = routeKey(pathname);
  const metadata = INDEXABLE[key] || NON_INDEXABLE[key];
  if (!metadata) {
    return {
      ...INDEXABLE.landing,
      title: `Page not found | ${SITE_NAME}`,
      robots: "noindex,follow",
    };
  }
  return {
    ...metadata,
    robots: key in NON_INDEXABLE ? "noindex,follow" : "index,follow,max-image-preview:large",
  };
}

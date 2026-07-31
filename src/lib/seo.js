export const SITE_URL = "https://assamflood.org";
export const SITE_NAME = "Axom Flood";
export const SOCIAL_IMAGE = `${SITE_URL}/social-card.jpg`;

const INDEXABLE = {
  // The river map is the site's front door. `/` used to be a search-only
  // landing page that bounced visitors to `/home/`, so the map now lives here
  // and the explanatory page moved to `/about/`.
  home: {
    title: "Assam Flood Information, River Levels and Alerts | Axom Flood",
    description:
      "Check Assam flood alerts, official river measurements, relief camp information and emergency contacts in plain language.",
    path: "/",
  },
  about: {
    title: "How Axom Flood Reads Assam River Levels | Axom Flood",
    description:
      "How Axom Flood turns official CWC river measurements into plain language, which sources it uses, and what its published limits are.",
    path: "/about/",
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
  terms: {
    title: "Terms of Use | Axom Flood",
    description:
      "What Axom Flood is, which government sources its Assam river and flood data comes from, and why it must not be used alone for safety decisions.",
    path: "/terms/",
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
  return pathname.split("/").filter(Boolean)[0] || "home";
}

export function metadataForPath(pathname) {
  const key = routeKey(pathname);
  const metadata = INDEXABLE[key] || NON_INDEXABLE[key];
  if (!metadata) {
    return {
      ...INDEXABLE.home,
      title: `Page not found | ${SITE_NAME}`,
      robots: "noindex,follow",
    };
  }
  return {
    ...metadata,
    robots: key in NON_INDEXABLE ? "noindex,follow" : "index,follow,max-image-preview:large",
  };
}

import { SITE_NAME, SITE_URL } from "./seo.js";

export function serializeJsonLd(value) {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}

export const faqItems = [
  {
    question: "Where can I check Assam flood status today?",
    answer:
      "Open the river bulletin and search for a village, revenue circle or district. Axom Flood shows the latest available official measurement, its age, the river trend and the source.",
  },
  {
    question: "Does Axom Flood show live Assam river levels?",
    answer:
      "Axom Flood publishes current CWC river measurements when the source is available. Every reading shows its observation time. A reading older than six hours is replaced with a no-data message instead of being presented as current.",
  },
  {
    question: "Where can I find Assam flood relief camp information?",
    answer:
      "Choose your area and open Relief camps. Listings come from published district documents. Camp status and locations can change, so call the listed contact or district authority before travelling.",
  },
  {
    question: "Which Assam flood emergency number should I call?",
    answer:
      "Open Emergency for the reviewed state-level contact saved in the current data bundle. The page clearly states what is not covered. Use district control-room or locally issued numbers when available.",
  },
  {
    question: "Is Axom Flood an official government website?",
    answer:
      "No. Axom Flood is an independent public-interest service that interprets and links to official measurements and published documents. It does not replace CWC, ASDMA or local authority warnings.",
  },
  {
    question: "Can I use the Assam flood bulletin without internet?",
    answer:
      "Yes, after the app and a bulletin have been saved on the device. Axom Flood recalculates the age of cached information and hides stale river numbers after six hours.",
  },
];

export const websiteSchema = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: SITE_NAME,
  alternateName: "Assam Flood",
  url: SITE_URL,
  description:
    "Plain-language Assam flood alerts, official river measurements, relief camp information and emergency contacts.",
  inLanguage: "en-IN",
  areaServed: {
    "@type": "AdministrativeArea",
    name: "Assam",
  },
};

export const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqItems.map(item => ({
    "@type": "Question",
    name: item.question,
    acceptedAnswer: {
      "@type": "Answer",
      text: item.answer,
    },
  })),
};

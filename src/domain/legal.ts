export const legalDocuments = {
  privacy: {
    title: "Политика обработки персональных данных",
    shortTitle: "политику обработки персональных данных",
    url: "https://docs.google.com/document/d/1Uj-TcHllfdAqBW9AbrkIbAvE7pjW1QiKRmRrVUm2oaI/edit?usp=sharing",
  },
  terms: {
    title: "Пользовательское соглашение",
    shortTitle: "пользовательское соглашение",
    url: "https://docs.google.com/document/d/1kJKiAgMONf2_i_Xkf_B-2m3SYMXIkGp0BEAKBHbIEGY/edit?usp=sharing",
  },
  offer: {
    title: "Публичная оферта",
    shortTitle: "публичную оферту",
    url: "https://docs.google.com/document/d/11HXCfabkmYSBZoEU1rVs05PVWiFpuDaWd0I3T19Gd9E/edit?usp=sharing",
  },
  personalDataConsent: {
    title: "Согласие на обработку персональных данных",
    shortTitle: "согласие на обработку персональных данных",
    url: "https://docs.google.com/document/d/15_1LX-A8g2TT8fhF7CUnDHeDOp4uyouIvzxEAYWxa-o/edit?usp=sharing",
  },
  marketingConsent: {
    title: "Согласие на рекламно-информационную рассылку",
    shortTitle: "согласие на рекламно-информационную рассылку",
    url: "https://docs.google.com/document/d/1un1kDiBb_C9P-AR_--UZJgvcTdDiBeSZsztOceV1lqQ/edit?usp=sharing",
  },
} as const;

export type LegalDocumentId = keyof typeof legalDocuments;

export const siteRequiredLegalDocumentIds = ["terms", "privacy", "personalDataConsent"] as const;
export const paymentRequiredLegalDocumentIds = ["offer", "terms", "privacy", "personalDataConsent"] as const;
export const footerLegalDocumentIds = [
  "privacy",
  "terms",
  "offer",
  "personalDataConsent",
  "marketingConsent",
] as const;

export const lessonCompletionAcknowledgementText =
  "Подтверждаю, что изучил(а) урок, материалы открылись корректно, содержание урока понятно, а при вопросах я обращусь в поддержку.";

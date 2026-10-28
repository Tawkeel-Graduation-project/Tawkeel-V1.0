/**
 * Locale helpers. Everything user-facing should be formatted through these so
 * the digit style stays consistent across screens.
 *
 * We use Arabic text with Western (Latin) digits ("ar-EG-u-nu-latn"), which is
 * common in Egyptian apps and keeps article/case numbers unambiguous.
 * Switch to "ar-EG" for Arabic-Indic digits (٠١٢٣) — one line change.
 */
export const LOCALE = "ar-EG-u-nu-latn";

export function formatNumber(value: number, options?: Intl.NumberFormatOptions) {
  return new Intl.NumberFormat(LOCALE, options).format(value);
}

export function formatCurrencyEGP(value: number) {
  return formatNumber(value, { style: "currency", currency: "EGP", maximumFractionDigits: 0 });
}

export function formatDate(value: Date | string | number, options?: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", ...options }).format(new Date(value));
}

export function formatDateTime(value: Date | string | number) {
  return formatDate(value, { dateStyle: "medium", timeStyle: "short" });
}

export function formatTime(value: Date | string | number) {
  return new Intl.DateTimeFormat(LOCALE, { timeStyle: "short" }).format(new Date(value));
}

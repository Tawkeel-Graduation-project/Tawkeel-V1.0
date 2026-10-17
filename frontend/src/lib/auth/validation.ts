/** Client-side checks for the auth forms. The backend validates again. */

/** Convert Arabic-Indic (٠-٩) and Persian (۰-۹) digits to ASCII and drop spaces/dashes. */
export function normalizeDigits(value: string) {
  return value
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/[\s-]/g, "");
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
/** Egyptian mobile: 010 / 011 / 012 / 015 + 8 digits. */
const EG_MOBILE_RE = /^01[0125]\d{8}$/;

export const isEmail = (v: string) => EMAIL_RE.test(v.trim());
export const isEgyptianMobile = (v: string) => EG_MOBILE_RE.test(normalizeDigits(v));

export const PASSWORD_MIN = 8;

export function passwordError(password: string): string | undefined {
  if (!password) return "أدخل كلمة المرور.";
  if (password.length < PASSWORD_MIN) return `كلمة المرور يجب ألا تقل عن ${PASSWORD_MIN} أحرف.`;
  if (!/[A-Za-z؀-ۿ]/.test(password) || !/\d/.test(normalizeDigits(password)))
    return "يجب أن تحتوي كلمة المرور على حروف وأرقام.";
  return undefined;
}

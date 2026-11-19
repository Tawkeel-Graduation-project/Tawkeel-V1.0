/**
 * Standard error model for the frontend.
 * API calls should throw `AppError` so every screen can show the same Arabic
 * message for the same kind of failure via <ErrorState />.
 */
export type AppErrorKind =
  | "network"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "validation"
  | "server"
  | "unknown";

export class AppError extends Error {
  constructor(
    public kind: AppErrorKind,
    message?: string,
    public status?: number,
  ) {
    super(message ?? kind);
    this.name = "AppError";
  }

  /** Map an HTTP status (e.g. from the FastAPI backend) to an AppError. */
  static fromStatus(status: number, message?: string) {
    const kind: AppErrorKind =
      status === 401
        ? "unauthorized"
        : status === 403
          ? "forbidden"
          : status === 404
            ? "not_found"
            : status === 400 || status === 422
              ? "validation"
              : status >= 500
                ? "server"
                : "unknown";
    return new AppError(kind, message, status);
  }
}

export const errorCopy: Record<AppErrorKind, { title: string; description: string }> = {
  network: {
    title: "تعذّر الاتصال",
    description: "تحقّق من اتصالك بالإنترنت ثم حاول مرة أخرى.",
  },
  unauthorized: {
    title: "انتهت الجلسة",
    description: "يرجى تسجيل الدخول مرة أخرى للمتابعة.",
  },
  forbidden: {
    title: "غير مسموح",
    description: "ليست لديك صلاحية للوصول إلى هذه الصفحة.",
  },
  not_found: {
    title: "غير موجود",
    description: "لم نعثر على ما تبحث عنه. ربما تم نقله أو حذفه.",
  },
  validation: {
    title: "بيانات غير صحيحة",
    description: "يرجى مراجعة الحقول المظللة وتصحيحها.",
  },
  server: {
    title: "حدث خطأ في الخادم",
    description: "واجهنا مشكلة من جهتنا. حاول مرة أخرى بعد قليل.",
  },
  unknown: {
    title: "حدث خطأ غير متوقع",
    description: "حاول مرة أخرى. إذا تكررت المشكلة، تواصل مع الدعم.",
  },
};

/**
 * Copy for legal-assistant reply notices (chat). Kinds match the backend
 * `ReplyKind` codes, plus "unsupported_claims" for answers with statements
 * that no source backs. A `message_ar` from the backend, when present,
 * replaces `description`.
 */
export type ChatNoticeCopyKind =
  | "clarification"
  | "no_source"
  | "invalid_question"
  | "temporarily_unavailable"
  | "answer_failed"
  | "unsupported_claims";

export const chatNoticeCopy: Record<ChatNoticeCopyKind, { title: string; description: string }> = {
  clarification: {
    title: "نحتاج إلى توضيح",
    description: "لنتمكن من الإجابة بدقة، نحتاج إلى توضيح بسيط منك.",
  },
  no_source: {
    title: "لم يُعثر على سند قانوني مؤكد لهذا الاستفسار",
    description:
      "لم يُعثر على سند قانوني مؤكد لهذا الاستفسار. يمكنك إعادة صياغة السؤال أو طلب استشارة محامٍ متخصص.",
  },
  invalid_question: {
    title: "تعذّر قراءة السؤال",
    description: "تعذّر قراءة السؤال. يرجى كتابة سؤالك القانوني بوضوح وباختصار ثم المحاولة مرة أخرى.",
  },
  temporarily_unavailable: {
    title: "المساعد القانوني غير متاح مؤقتاً",
    description: "المساعد القانوني غير متاح مؤقتاً. حاول مرة أخرى بعد قليل، أو اطلب استشارة محامٍ متخصص.",
  },
  answer_failed: {
    title: "حدث خطأ أثناء صياغة الإجابة",
    description: "تعذّر صياغة إجابة موثّقة لهذا السؤال. حاول مرة أخرى، أو اطلب استشارة محامٍ متخصص.",
  },
  unsupported_claims: {
    title: "عبارات غير موثّقة",
    description: "بعض العبارات في هذه الإجابة غير مدعومة بسند من المصادر المعروضة، فيرجى التعامل معها بحذر.",
  },
};

/** Default actions per failure kind, mirroring the backend table. */
export const chatNoticeActions: Record<
  "invalid_question" | "temporarily_unavailable" | "answer_failed",
  { retryable: boolean; showLawyerCta: boolean }
> = {
  invalid_question: { retryable: true, showLawyerCta: false },
  temporarily_unavailable: { retryable: true, showLawyerCta: true },
  answer_failed: { retryable: true, showLawyerCta: true },
};

/** Normalise anything thrown into an error kind. */
export function getErrorKind(error: unknown): AppErrorKind {
  if (error instanceof AppError) return error.kind;
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) return "network";
  return "unknown";
}

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

/** Normalise anything thrown into an error kind. */
export function getErrorKind(error: unknown): AppErrorKind {
  if (error instanceof AppError) return error.kind;
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) return "network";
  return "unknown";
}

import type { IntakeErrorCode, IntakePhase } from "./api";

export const intakeErrorCopy: Record<IntakeErrorCode, string> = {
  no_answer: "يمكن طلب محامٍ بعد أن يجيب المساعد على سؤالك أولاً.",
  unauthorized: "انتهت جلستك. يرجى تسجيل الدخول مرة أخرى ثم المحاولة.",
  forbidden: "ليس لديك صلاحية للوصول إلى هذا الطلب.",
  not_found: "لم يتم العثور على هذا الطلب.",
  conflict: "تم تحديث الطلب من مكان آخر. أعدنا تحميل آخر نسخة، يرجى المتابعة.",
  network: "تعذّر الاتصال بالخادم. تحقّق من اتصالك بالإنترنت ثم أعد المحاولة.",
  unknown: "حدث خطأ غير متوقع أثناء بدء طلب المحامي. يرجى المحاولة مرة أخرى.",
};

export const intakePhaseLabel: Record<IntakePhase, string> = {
  INTAKE: "جمع معلومات القضية",
};

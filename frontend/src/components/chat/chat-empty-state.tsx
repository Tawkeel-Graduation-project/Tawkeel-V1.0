import { Scale, Sparkles, HelpCircle } from "lucide-react";
import { SUGGESTED_QUESTIONS, type SuggestedQuestion } from "@/lib/chat/types";
import { Badge } from "@/components/ui";

interface ChatEmptyStateProps {
  onSelectQuestion: (question: string) => void;
}

export function ChatEmptyState({ onSelectQuestion }: ChatEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-6 text-center sm:py-10">
      {/* Decorative badge & emblem */}
      <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-vivid/20 bg-primary-soft/60 px-3.5 py-1.5 text-xs font-semibold text-primary">
        <Sparkles aria-hidden className="size-3.5 text-vivid" />
        <span>مساعد قانوني معتمد بالتشريعات المصرية</span>
      </div>

      <div className="relative mb-5 flex size-16 items-center justify-center rounded-2xl bg-linear-to-br from-vivid-2 via-vivid to-primary text-white shadow-xl shadow-vivid/25">
        <Scale aria-hidden className="size-8" />
        <span className="absolute -bottom-1 -end-1 flex size-5 items-center justify-center rounded-full bg-secondary text-[10px] text-white">
          AI
        </span>
      </div>

      <h2 className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
        كيف يمكنني مساعدتك قانونياً اليوم؟
      </h2>
      <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">
        اطرح أي استفسار حول حقوقك والتزاماتك في القانون المصري، وسأستخرج لك المواد والنصوص القانونية المؤيدة للإجابة فوراً.
      </p>

      {/* Suggested prompts list */}
      <div className="mt-8 w-full max-w-2xl">
        <div className="mb-3 flex items-center justify-between px-1 text-xs font-medium text-muted">
          <span className="inline-flex items-center gap-1.5">
            <HelpCircle aria-hidden className="size-3.5 text-vivid" />
            نماذج أسئلة شائعة يمكنك البدء بها:
          </span>
          <span>انقر لطرح السؤال</span>
        </div>

        <div className="grid gap-2.5 sm:grid-cols-2">
          {SUGGESTED_QUESTIONS.map((item: SuggestedQuestion) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectQuestion(item.question)}
              className="group flex flex-col items-start gap-1.5 rounded-xl border border-border bg-surface p-3.5 text-start transition-all hover:-translate-y-0.5 hover:border-vivid/50 hover:bg-primary-soft/30 hover:shadow-sm"
            >
              <div className="flex w-full items-center justify-between">
                <Badge tone="neutral" className="text-[11px]">
                  {item.category}
                </Badge>
                <span className="text-xs font-semibold text-primary opacity-0 transition-opacity group-hover:opacity-100">
                  اسأل الآن ←
                </span>
              </div>
              <p className="text-xs leading-relaxed font-medium text-foreground group-hover:text-primary">
                {item.question}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

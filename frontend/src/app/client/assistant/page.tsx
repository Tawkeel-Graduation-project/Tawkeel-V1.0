import type { Metadata } from "next";
import { ChatScreen } from "@/components/chat/chat-screen";

export const metadata: Metadata = {
  title: "المساعد القانوني",
  description: "اسأل سؤالًا قانونيًا واحصل على إجابة موثّقة بالنصوص والتشريعات المصرية",
};

export default function AssistantPage() {
  return <ChatScreen />;
}

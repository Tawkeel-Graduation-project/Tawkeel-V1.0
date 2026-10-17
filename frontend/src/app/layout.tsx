import type { Metadata } from "next";
// Self-hosted Arabic font (no runtime call to Google Fonts, works offline/on-prem).
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/500.css";
import "@fontsource/ibm-plex-sans-arabic/600.css";
import "@fontsource/ibm-plex-sans-arabic/700.css";
import "./globals.css";
import { AuthProvider } from "@/lib/auth/auth-context";

export const metadata: Metadata = {
  title: {
    default: "توكيل",
    template: "%s | توكيل",
  },
  description: "منصة توكيل: مساعد قانوني ذكي للمحامين والعملاء في مصر",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The whole product is Arabic-first: direction is set once, at the root.
    <html lang="ar" dir="rtl" className="h-full antialiased">
      <body className="min-h-full">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}

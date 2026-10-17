"use client";

/**
 * Last-resort boundary (errors in the root layout itself). It replaces the
 * root layout, so it must render its own <html>/<body> and can't rely on
 * providers — keep it dependency-free and inline-styled.
 */
export default function GlobalError({ retry }: { error: unknown; retry: () => void }) {
  return (
    <html lang="ar" dir="rtl">
      <body
        style={{
          fontFamily: "system-ui, Tahoma, sans-serif",
          display: "grid",
          placeItems: "center",
          minHeight: "100vh",
          margin: 0,
          background: "#f6f5f1",
          color: "#1c1f24",
        }}
      >
        <div style={{ textAlign: "center", padding: 24 }}>
          <h1 style={{ fontSize: 20, marginBottom: 8 }}>حدث خطأ غير متوقع</h1>
          <p style={{ color: "#5d6470", marginBottom: 20 }}>نعتذر عن ذلك. حاول تحميل الصفحة مرة أخرى.</p>
          <button
            onClick={() => retry()}
            style={{
              background: "#1f4e5f",
              color: "#fff",
              border: 0,
              borderRadius: 8,
              padding: "10px 20px",
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            إعادة المحاولة
          </button>
        </div>
      </body>
    </html>
  );
}

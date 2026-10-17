# Tawkeel — Frontend

The Arabic-first (RTL) web app for Tawkeel, built with Next.js 16 (App Router), TypeScript and Tailwind CSS v4.

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run build && npm start
npm run lint
```

> Next.js 16 changes some APIs: error boundaries receive `retry` instead of `reset`, and `cacheComponents` is on.
> See `AGENTS.md` and `node_modules/next/dist/docs/` before using a Next API you haven't used before.

## What's here (sprint story: Arabic-first RTL app shell)

| Acceptance criterion | Where |
|---|---|
| RTL layout | `<html lang="ar" dir="rtl">` in `src/app/layout.tsx`. Use **logical** Tailwind classes only (`ms-/me-`, `ps-/pe-`, `start-/end-`, `border-s/e`, `text-start`), never `ml-/mr-/left-/right-`. |
| Theme | Design tokens are in `src/app/globals.css` (light and dark). Use semantic classes like `bg-surface`, `text-muted`, `bg-primary`, `text-danger`. |
| Shared components | `src/components/ui/*`, imported from `@/components/ui`. You can browse them live at **`/ui`**. |
| Role-based navigation | `src/lib/navigation.ts` is the single source of truth for each role's menu. `AppShell` + `RoleGuard` live in `src/components/shell/`. |
| Standard error/loading states | `LoadingState`, `ErrorState`, `EmptyState`, `PageSkeleton`, `AsyncView` (`ui/states.tsx`), plus the route files `loading.tsx` / `error.tsx` / `not-found.tsx` / `global-error.tsx`. Arabic error copy and the `AppError` model are in `src/lib/errors.ts`. |

## Conventions for new screens

1. Put the page under `src/app/client/...` or `src/app/lawyer/...`. It automatically gets the shell, the role guard, a loading skeleton and an error boundary.
2. Add the page to `src/lib/navigation.ts` if it belongs in the menu.
3. Start the page with `<PageHeader title=… description=… />`.
4. For async data, wrap the result in `<AsyncView status error onRetry isEmpty empty>`. Don't hand-roll spinners or error messages.
5. From API calls, throw `AppError.fromStatus(res.status)` so the user sees the standard Arabic message.
6. If an icon implies direction (arrows, chevrons), wrap it in `<DirectionalIcon>` so it mirrors in RTL.
7. Format numbers, money and dates with `src/lib/format.ts`. It uses Western digits; to switch to Arabic-Indic digits, set `LOCALE = "ar-EG"`.
8. Write emails, URLs and code inline with `dir="ltr"`.

## Auth is mocked (for now)

`src/lib/auth/auth-context.tsx` stores the chosen role in `localStorage`. The sign-in page (`/`) lets you pick **client** or **lawyer**. While mocked, a dashed "تجريبي" (demo) switcher in the top bar lets you swap roles; set `NEXT_PUBLIC_MOCK_AUTH=false` to hide it.

When the FastAPI JWT story lands:

- Replace the store inside `auth-context.tsx` and keep the `useAuth()` shape (`user`, `status`, `signIn`, `signOut`).
- Add `src/proxy.ts` to redirect by role on the server.
- The client-side guard is **UX only**. RBAC must still be enforced by the backend (PRD §10).

## Font

IBM Plex Sans Arabic is self-hosted through `@fontsource`, so there's no runtime call to Google. This keeps working offline and for local/firm deployment.

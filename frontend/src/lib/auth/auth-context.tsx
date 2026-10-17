"use client";

/**
 * Client-side session store.
 *
 * Holds the session returned by `lib/auth/api.ts` (user + token + expiry) in
 * localStorage and drops it once it expires. Screens read it through
 * `useAuth()`.
 *
 * The client-side role check here is for UX only — it is NOT a security
 * boundary. RBAC must be enforced by the backend (PRD §10).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import type { Session } from "./api";
import type { Role, SessionUser } from "./types";

const STORAGE_KEY = "tawkeel.session";
/** Set when a session times out, so the login screen can say why. */
const EXPIRED_FLAG_KEY = "tawkeel.sessionExpired";

/** Used only by the demo role switcher while the backend is mocked. */
const mockUsers: Record<Role, SessionUser> = {
  client: { id: "u-client-1", name: "أحمد محمود", email: "client@example.com", role: "client" },
  lawyer: { id: "u-lawyer-1", name: "أ. سارة عبد الرحمن", email: "lawyer@example.com", role: "lawyer" },
};

// --- tiny external store over localStorage --------------------------------
const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedSession: Session | null = null;

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function parse(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const s = JSON.parse(raw) as Session;
    return s?.user && typeof s.expiresAt === "number" ? s : null;
  } catch {
    return null;
  }
}

function getSnapshot(): Session | null {
  const raw = readRaw();
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedSession = parse(raw);
  }
  return cachedSession && cachedSession.expiresAt > Date.now() ? cachedSession : null;
}

/** On the server (and during hydration) the session is not known yet. */
function getServerSnapshot(): undefined {
  return undefined;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => e.key === STORAGE_KEY && listener();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function write(session: Session | null) {
  try {
    if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable (private mode) — session lasts for this tab only */
  }
  listeners.forEach((l) => l());
}

function markExpired() {
  try {
    window.sessionStorage.setItem(EXPIRED_FLAG_KEY, "1");
  } catch {
    /* ignore */
  }
  write(null);
}

/** Returns true once if the last session ended by timing out. */
export function consumeSessionExpired(): boolean {
  try {
    const expired = window.sessionStorage.getItem(EXPIRED_FLAG_KEY) === "1";
    window.sessionStorage.removeItem(EXPIRED_FLAG_KEY);
    return expired;
  } catch {
    return false;
  }
}
// ---------------------------------------------------------------------------

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: SessionUser | null;
  token: string | null;
  status: AuthStatus;
  /** Store the session returned by login / register. */
  startSession: (session: Session) => void;
  /** Demo only: sign in as the mock user of a role (role switcher). */
  signIn: (role: Role) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const snapshot = useSyncExternalStore<Session | null | undefined>(subscribe, getSnapshot, getServerSnapshot);

  // A stored session that is already past its expiry (e.g. after reopening the tab).
  useEffect(() => {
    if (snapshot === null && parse(readRaw())) markExpired();
  }, [snapshot]);

  // End the session the moment it expires.
  const expiresAt = snapshot?.expiresAt;
  useEffect(() => {
    if (!expiresAt) return;
    const t = window.setTimeout(markExpired, Math.max(0, expiresAt - Date.now()));
    return () => window.clearTimeout(t);
  }, [expiresAt]);

  const startSession = useCallback((session: Session) => write(session), []);
  const signIn = useCallback(
    (role: Role) =>
      write({
        user: mockUsers[role],
        token: `mock.${role}`,
        expiresAt: getSnapshot()?.expiresAt ?? Date.now() + 60 * 60 * 1000,
      }),
    [],
  );
  const signOut = useCallback(() => write(null), []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: snapshot?.user ?? null,
      token: snapshot?.token ?? null,
      status: snapshot === undefined ? "loading" : snapshot ? "authenticated" : "unauthenticated",
      startSession,
      signIn,
      signOut,
    }),
    [snapshot, startSession, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

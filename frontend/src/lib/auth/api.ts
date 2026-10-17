/**
 * Auth API used by the login / register screens.
 *
 * When NEXT_PUBLIC_API_URL is set, requests go to the FastAPI backend:
 *
 *   POST {API}/auth/register  { name, email, phone?, password, role }
 *     201 -> AuthResponse      409 -> email already registered
 *   POST {API}/auth/login     { identifier, password }   (identifier = email or phone)
 *     200 -> AuthResponse      401 -> invalid credentials
 *
 *   AuthResponse = { access_token, token_type: "bearer", expires_in: <seconds>,
 *                    user: { id, name, email, role } }
 *
 * Password hashing, token signing and expiry are the backend's job. Without
 * NEXT_PUBLIC_API_URL a browser-only mock answers instead, so the screens can
 * be demoed before the backend exists. The mock is NOT secure.
 */
import type { Role, SessionUser } from "./types";

export interface Session {
  user: SessionUser;
  token: string;
  /** Epoch ms after which the session is no longer valid. */
  expiresAt: number;
}

export interface RegisterInput {
  name: string;
  email: string;
  phone?: string;
  password: string;
  role: Role;
}

export interface LoginInput {
  identifier: string;
  password: string;
}

export type AuthErrorCode = "invalid_credentials" | "email_taken" | "network" | "unknown";

export class AuthError extends Error {
  constructor(public code: AuthErrorCode) {
    super(code);
  }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

export function register(input: RegisterInput): Promise<Session> {
  return API_URL ? post("/auth/register", input, { 409: "email_taken" }) : mock.register(input);
}

export function login(input: LoginInput): Promise<Session> {
  return API_URL ? post("/auth/login", input, { 401: "invalid_credentials" }) : mock.login(input);
}

// --- real backend -----------------------------------------------------------
interface AuthResponse {
  access_token: string;
  expires_in: number;
  user: SessionUser;
}

async function post(path: string, body: unknown, errors: Record<number, AuthErrorCode>): Promise<Session> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthError("network");
  }
  if (!res.ok) throw new AuthError(errors[res.status] ?? "unknown");
  const data = (await res.json()) as AuthResponse;
  return { user: data.user, token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
}

// --- browser-only mock --------------------------------------------------------
const MOCK_USERS_KEY = "tawkeel.mockUsers";
const MOCK_SESSION_TTL_MS = 60 * 60 * 1000; // 1 hour, like a short-lived JWT

interface MockUserRecord extends SessionUser {
  phone?: string;
  salt: string;
  passwordHash: string;
}

/** Demo accounts, shown on the login screen while the mock is active. */
export const MOCK_DEMO_PASSWORD = "Tawkeel2026";
const demoSeed: (SessionUser & { phone?: string })[] = [
  { id: "u-client-1", name: "أحمد محمود", email: "client@example.com", phone: "01012345678", role: "client" },
  { id: "u-lawyer-1", name: "أ. سارة عبد الرحمن", email: "lawyer@example.com", role: "lawyer" },
];

async function sha256(text: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password: string, salt: string) {
  return sha256(`${salt}:${password}`);
}

function readUsers(): MockUserRecord[] {
  try {
    return JSON.parse(window.localStorage.getItem(MOCK_USERS_KEY) ?? "[]") as MockUserRecord[];
  } catch {
    return [];
  }
}

function writeUsers(users: MockUserRecord[]) {
  try {
    window.localStorage.setItem(MOCK_USERS_KEY, JSON.stringify(users));
  } catch {
    /* storage unavailable — accounts last for this page only */
  }
}

async function allUsers(): Promise<MockUserRecord[]> {
  const users = readUsers();
  for (const seed of demoSeed) {
    if (users.some((u) => u.email === seed.email)) continue;
    const salt = crypto.randomUUID();
    users.push({ ...seed, salt, passwordHash: await hashPassword(MOCK_DEMO_PASSWORD, salt) });
  }
  return users;
}

function toSession({ id, name, email, role }: MockUserRecord): Session {
  return { user: { id, name, email, role }, token: `mock.${crypto.randomUUID()}`, expiresAt: Date.now() + MOCK_SESSION_TTL_MS };
}

const delay = () => new Promise((r) => setTimeout(r, 500));

const mock = {
  async register(input: RegisterInput): Promise<Session> {
    await delay();
    const users = await allUsers();
    const email = input.email.toLowerCase();
    if (users.some((u) => u.email === email)) throw new AuthError("email_taken");
    const salt = crypto.randomUUID();
    const record: MockUserRecord = {
      id: `u-${crypto.randomUUID()}`,
      name: input.name,
      email,
      phone: input.phone,
      role: input.role,
      salt,
      passwordHash: await hashPassword(input.password, salt),
    };
    writeUsers([...users, record]);
    return toSession(record);
  },

  async login({ identifier, password }: LoginInput): Promise<Session> {
    await delay();
    const users = await allUsers();
    writeUsers(users);
    const id = identifier.toLowerCase();
    const user = users.find((u) => u.email === id || (u.phone && u.phone === id));
    // Same error whether the account is missing or the password is wrong.
    if (!user || (await hashPassword(password, user.salt)) !== user.passwordHash) {
      throw new AuthError("invalid_credentials");
    }
    return toSession(user);
  },
};

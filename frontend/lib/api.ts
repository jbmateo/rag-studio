import type { User } from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  // Bad credentials on the auth pages are a normal error, not an expired session.
  const onAuthPage = typeof window !== "undefined" && /^\/(login|signup)/.test(window.location.pathname);
  if (res.status === 401 && typeof window !== "undefined" && !onAuthPage) {
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const me = () => api<User>("/api/auth/me");
export const login = (email: string, password: string, remember: boolean) =>
  api<User>("/api/auth/login", json({ email, password, remember }));
export const signup = (email: string, password: string) =>
  api<User>("/api/auth/signup", json({ email, password }));
export const logout = () => api<void>("/api/auth/logout", { method: "POST" });

/** Friendly message for auth form errors. */
export function authErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 409) return "An account with this email already exists.";
    if (e.status === 422 || Array.isArray(e.detail))
      return "Please enter a valid email and a password of 8–72 characters.";
    if (typeof e.detail === "string" && e.detail) return e.detail;
  }
  return "Something went wrong. Please try again.";
}

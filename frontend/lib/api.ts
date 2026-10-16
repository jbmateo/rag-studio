import { useCallback, useEffect, useRef, useState } from "react";
import type { AskResponse, ChunkRow, Document, User } from "./types";

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
  const onAuthPage = typeof window !== "undefined" && /^\/(login|signup)(\/|$)/.test(window.location.pathname);
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

export const listDocuments = () => api<Document[]>("/api/documents");
export const deleteDocument = (id: string) => api<void>(`/api/documents/${id}`, { method: "DELETE" });
export const uploadFiles = (files: File[]) => {
  const body = new FormData();
  for (const f of files) body.append("files", f);
  return api<Document[]>("/api/documents", { method: "POST", body });
};
export const importUrl = (url: string) => api<Document[]>("/api/documents", json({ url }));

/** Friendly message for document errors (400 detail, 413 too large). */
export function documentErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 413) return "Upload is too large (100 MB maximum).";
    if (typeof e.detail === "string" && e.detail) return e.detail;
  }
  return "Something went wrong. Please try again.";
}

/** The user's documents; polls every 2 s only while any is still processing. */
export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const docs = await listDocuments();
      if (!alive.current) return;
      setDocuments(docs);
      setError(null);
    } catch (e) {
      if (alive.current) setError(documentErrorMessage(e));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    refresh();
    return () => {
      alive.current = false;
    };
  }, [refresh]);

  const processing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!processing) return;
    const id = setInterval(refresh, 2000);
    return () => clearInterval(id);
  }, [processing, refresh]);

  return { documents, refresh, error, loading };
}

export const askQuestion = (question: string, docIds: string[] | null) =>
  api<AskResponse>("/api/ask", json({ question, doc_ids: docIds }));
export const listChunks = (docId: string, offset = 0, limit = 50) =>
  api<ChunkRow[]>(`/api/documents/${docId}/chunks?offset=${offset}&limit=${limit}`);

/** Friendly message for ask errors; 400 "Upload a document first" is handled by the caller as info. */
export function askErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 422) return "Please enter a question.";
    if (typeof e.detail === "string" && e.detail) return e.detail;
  }
  return "Something went wrong. Please try again.";
}

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { authErrorMessage, login, signup } from "@/lib/api";

const input =
  "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40";

export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isLogin = mode === "login";

  // Submit stays disabled until hydrated so an early click can't fall back to a native form post.
  useEffect(() => setReady(true), []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const form = new FormData(e.currentTarget as HTMLFormElement);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    setError(null);
    setBusy(true);
    try {
      if (isLogin) await login(email, password, remember);
      else await signup(email, password);
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
      router.refresh();
    } catch (err) {
      setError(authErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="text-sm font-semibold tracking-wide text-indigo-600">RAG Studio</div>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">
            {isLogin ? "Welcome back" : "Create your account"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {isLogin ? "Log in to ask questions about your documents." : "Start asking questions about your documents."}
          </p>
        </div>
        <form onSubmit={onSubmit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700">Email</label>
            <input id="email" name="email" type="email" required autoComplete="email" className={input} />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700">Password</label>
            <input id="password" name="password" type="password" required minLength={8} maxLength={72}
              autoComplete={isLogin ? "current-password" : "new-password"} className={input} />
          </div>
          {isLogin && (
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-2 focus:ring-indigo-500/40" />
              Remember me
            </label>
          )}
          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          )}
          <button type="submit" disabled={busy || !ready}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:opacity-60">
            {isLogin ? "Log in" : "Sign up"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-600">
          {/* plain anchors (full page load) avoid a client-nav race with early form fills */}
          {isLogin ? (
            <a href="/signup" className="font-medium text-indigo-600 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">Create an account</a>
          ) : (
            <>Already have an account?{" "}
              <a href="/login" className="font-medium text-indigo-600 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">Log in</a></>
          )}
        </p>
      </div>
    </main>
  );
}

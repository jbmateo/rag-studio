"use client";

import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { documentErrorMessage, importUrl, uploadFiles } from "@/lib/api";

const input =
  "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40";

export default function UploadPanel({ onChanged }: { onChanged: () => Promise<void> | void }) {
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      await onChanged();
      return true;
    } catch (e) {
      setError(documentErrorMessage(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function sendFiles(list: FileList | null) {
    const files = list ? Array.from(list) : [];
    if (files.length) await run(() => uploadFiles(files));
    if (fileInput.current) fileInput.current.value = "";
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!busy) sendFiles(e.dataTransfer.files);
  }

  async function onImport(e: FormEvent) {
    e.preventDefault();
    const value = url.trim();
    if (!value) return;
    if (await run(() => importUrl(value))) setUrl("");
  }

  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`relative rounded-xl border-2 border-dashed p-8 text-center text-sm focus-within:ring-2 focus-within:ring-indigo-500 ${
          dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-slate-50"
        }`}
      >
        <input ref={fileInput} type="file" multiple aria-label="Upload files" accept=".pdf,.docx,.md,.txt,.html"
          disabled={busy} onChange={(e) => sendFiles(e.target.files)}
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-wait" />
        {busy ? (
          <span className="font-medium text-indigo-600" role="status">Uploading…</span>
        ) : (
          <>
            <span className="font-medium text-slate-700">Drop files here or click to browse</span>
            <span className="mt-1 block text-slate-500">PDF, DOCX, MD, TXT or HTML, up to 20 MB each</span>
          </>
        )}
      </div>
      <form onSubmit={onImport} className="flex gap-2">
        <input type="url" aria-label="Import from URL" placeholder="https://…" value={url}
          onChange={(e) => setUrl(e.target.value)} className={input} />
        <button type="submit" disabled={busy || !url.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:opacity-50">
          Import
        </button>
      </form>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    </section>
  );
}

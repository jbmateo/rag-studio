"use client";

import { useDocuments } from "@/lib/api";
import DocumentsTable from "./DocumentsTable";
import UploadPanel from "./UploadPanel";

export default function DocumentsTab() {
  const { documents, refresh, error } = useDocuments();
  return (
    <div className="space-y-6">
      <UploadPanel onChanged={refresh} />
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <DocumentsTable documents={documents} onChanged={refresh} />
    </div>
  );
}

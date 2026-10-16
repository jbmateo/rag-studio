import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG Studio",
  description: "Ask questions about your documents, with cited answers.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}

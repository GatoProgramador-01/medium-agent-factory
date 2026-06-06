import type { Metadata } from "next";
import Link from "next/link";
import { NavLinks } from "@/components/NavLinks";
import "./globals.css";

export const metadata: Metadata = {
  title: "Medium Agent Factory",
  description: "Multi-agent automated Medium post pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <header className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--bg)]/90 backdrop-blur-sm px-6 py-3 flex items-center gap-6">
          <Link href="/" className="font-bold text-[var(--accent)] text-sm tracking-tight shrink-0">
            ✦ Medium Factory
          </Link>
          <NavLinks />
        </header>
        <main className="flex-1 px-6 py-8 max-w-6xl mx-auto w-full">
          {children}
        </main>
      </body>
    </html>
  );
}

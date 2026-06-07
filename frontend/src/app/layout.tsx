import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { NavLinks } from "@/components/NavLinks";
import "./globals.css";

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "medium-agent-factory",
  description: "Multi-agent automated Medium post pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={mono.className}>
      <body className="min-h-screen flex flex-col bg-[var(--bg)] text-[var(--text)]">
        {/* Terminal window chrome */}
        <div className="flex items-center gap-2 px-4 py-2 bg-[var(--surface)] border-b border-[var(--border)]">
          <span className="w-3 h-3 rounded-full bg-[var(--red)] opacity-80" />
          <span className="w-3 h-3 rounded-full bg-[var(--yellow)] opacity-80" />
          <span className="w-3 h-3 rounded-full bg-[var(--accent)] opacity-80" />
          <span className="ml-3 text-[var(--muted)] text-[11px] tracking-widest select-none">
            medium-agent-factory — bash
          </span>
        </div>

        {/* Nav bar */}
        <div className="border-b border-[var(--border)] bg-[var(--bg)] px-4 py-2 flex items-center gap-4">
          <Link href="/" className="text-[var(--accent)] text-xs font-bold tracking-widest hover:text-[var(--accent2)] transition-colors">
            ~/factory
          </Link>
          <span className="text-[var(--border2)]">|</span>
          <NavLinks />
        </div>

        {/* Content */}
        <main className="flex-1 px-6 py-6 max-w-5xl mx-auto w-full">
          {children}
        </main>
      </body>
    </html>
  );
}

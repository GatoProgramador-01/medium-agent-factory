import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Medium Agent Factory",
  description: "Multi-agent automated Medium post pipeline",
};

const nav = [
  { href: "/", label: "Dashboard" },
  { href: "/pipeline", label: "Run Pipeline" },
  { href: "/posts", label: "Posts" },
  { href: "/analytics", label: "Analytics" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-[var(--border)] px-6 py-4 flex items-center gap-8">
          <span className="font-bold text-[var(--accent)] text-lg tracking-tight">
            ✦ Medium Factory
          </span>
          <nav className="flex gap-6 text-sm text-[var(--muted)]">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className="hover:text-[var(--text)] transition-colors"
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="px-6 py-8 max-w-6xl mx-auto">{children}</main>
      </body>
    </html>
  );
}

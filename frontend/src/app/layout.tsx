import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { NavLinks } from "@/components/NavLinks";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });
const mono  = JetBrains_Mono({ subsets: ["latin"], display: "swap", variable: "--font-mono", weight: ["400","500","600"] });

export const metadata: Metadata = {
  title: "Medium Agent Factory",
  description: "Multi-agent AI writing pipeline for Medium",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`} style={{ fontFamily: "var(--font-inter), system-ui, sans-serif" }}>
      <body className="min-h-screen flex flex-col" style={{ background: "var(--bg)", color: "var(--text)" }}>

        {/* Header */}
        <header style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}>
          <div className="max-w-5xl mx-auto px-6 py-3 flex items-center gap-6">
            <Link
              href="/"
              className="font-semibold text-sm tracking-tight"
              style={{ color: "var(--orange)" }}
            >
              Agent Factory
            </Link>
            <div style={{ width: "1px", height: "16px", background: "var(--border-light)" }} />
            <NavLinks />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 max-w-5xl mx-auto w-full px-6 py-8">
          {children}
        </main>

      </body>
    </html>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/pipeline", label: "Run Pipeline" },
  { href: "/posts", label: "Posts" },
  { href: "/analytics", label: "Analytics" },
];

export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1">
      {NAV.map(({ href, label }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            data-testid={`nav-${label.toLowerCase().replace(/\s+/g, "-")}`}
            className={`
              px-3 py-1.5 rounded-md text-sm transition-colors
              ${active
                ? "text-[var(--text)] bg-[var(--accent-dim)]"
                : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--surface-hover)]"
              }
            `}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/",          label: "dashboard",  cmd: "~" },
  { href: "/pipeline",  label: "pipeline",   cmd: "run" },
  { href: "/posts",     label: "posts",      cmd: "ls"  },
  { href: "/analytics", label: "analytics",  cmd: "top" },
];

export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-1">
      {NAV.map(({ href, label, cmd }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            data-testid={`nav-${label}`}
            className={`
              px-3 py-1 text-xs transition-colors border
              ${active
                ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent-dim)]"
                : "border-transparent text-[var(--muted)] hover:text-[var(--text)] hover:border-[var(--border2)]"
              }
            `}
          >
            <span className="opacity-40">{cmd}/</span>{label}
          </Link>
        );
      })}
    </nav>
  );
}

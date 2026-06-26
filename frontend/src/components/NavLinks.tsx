"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/",          label: "Dashboard" },
  { href: "/pipeline",  label: "Pipeline"  },
  { href: "/posts",     label: "Posts"     },
  { href: "/series",    label: "Series"    },
  { href: "/exemplars", label: "Exemplars" },
  { href: "/analytics", label: "Analytics" },
];

export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-1">
      {NAV.map(({ href, label }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        const testId = `nav-${label.toLowerCase()}`;
        return (
          <Link
            key={href}
            href={href}
            data-testid={testId}
            className="px-3 py-1.5 rounded-md text-sm transition-colors"
            style={{
              color:         active ? "var(--orange)"  : "var(--text-muted)",
              background:    active ? "transparent"    : "transparent",
              fontWeight:    active ? 600               : 400,
              borderBottom:  active ? "2px solid var(--orange)" : "2px solid transparent",
              paddingBottom: "2px",
            }}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

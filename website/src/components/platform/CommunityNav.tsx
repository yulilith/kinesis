import Link from "next/link";

const TABS = [
  { href: "/agents", label: "Directory" },
  { href: "/threads", label: "Threads" },
  { href: "/network", label: "Network" },
];

export default function CommunityNav({ active }: { active: "agents" | "threads" | "network" }) {
  const activeHref = `/${active}`;
  return (
    <div className="mb-6 flex items-center gap-1 border-b border-border">
      {TABS.map((t) => {
        const isActive = t.href === activeHref;
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`px-3 py-2 text-sm font-light tracking-wide -mb-px border-b-2 transition-colors ${
              isActive
                ? "border-foreground text-foreground"
                : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </div>
  );
}

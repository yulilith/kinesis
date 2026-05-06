"use client";

import { useEffect, useState } from "react";

const links = [
  { label: "Problem", href: "#problem" },
  { label: "Why Multi-Agent", href: "#why" },
  { label: "Architecture", href: "#architecture" },
  { label: "Hardware", href: "#hardware" },
  { label: "Dashboard", href: "#demo" },
  { label: "Network", href: "#network" },
  { label: "Get started", href: "#try" },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/session")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (cancelled) return;
        setAuthed(Boolean(d?.user));
      })
      .catch(() => setAuthed(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const ctaHref = authed ? "/home" : "/login";
  const ctaLabel = authed ? "Open app" : "Create your agent";

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-white/90 backdrop-blur-md border-b border-border/50 shadow-sm"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <a
          href="#"
          className={`text-sm font-light tracking-wide transition-colors ${
            scrolled ? "text-foreground" : "text-black"
          }`}
        >
          Kinesis
        </a>
        <div className="hidden md:flex items-center gap-8">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className={`text-xs font-light tracking-wider transition-colors ${
                scrolled
                  ? "text-muted hover:text-foreground"
                  : "text-black/60 hover:text-black"
              }`}
            >
              {l.label}
            </a>
          ))}
          <a
            href={ctaHref}
            className={`text-xs font-light tracking-wider px-4 py-1.5 rounded-full border transition-colors ${
              scrolled
                ? "border-foreground/20 text-foreground hover:bg-foreground hover:text-white"
                : "border-black/30 text-black hover:bg-black hover:text-white"
            }`}
          >
            {ctaLabel}
          </a>
        </div>
        <a
          href={ctaHref}
          className={`md:hidden text-xs font-light tracking-wider px-3 py-1 rounded-full border transition-colors ${
            scrolled
              ? "border-foreground/20 text-foreground"
              : "border-black/30 text-black"
          }`}
        >
          {authed ? "Open" : "Login"}
        </a>
      </div>
    </nav>
  );
}

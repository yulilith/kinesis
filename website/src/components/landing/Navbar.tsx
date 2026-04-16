"use client";

import { useEffect, useState } from "react";

const links = [
  { label: "Problem", href: "#problem" },
  { label: "Why Multi-Agent", href: "#why" },
  { label: "Architecture", href: "#architecture" },
  { label: "Hardware", href: "#hardware" },
  { label: "Demo", href: "#demo" },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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
            scrolled ? "text-foreground" : "text-white"
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
                  : "text-white/60 hover:text-white"
              }`}
            >
              {l.label}
            </a>
          ))}
        </div>
      </div>
    </nav>
  );
}

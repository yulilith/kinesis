"use client";

import { useEffect, useRef, useState } from "react";

const reasons = [
  {
    title: "Different modalities, different timescales",
    points: [
      ["Body signals", "high-frequency, real-time"],
      ["Context signals", "lower frequency, semantic"],
      ["Behavior patterns", "long-term"],
    ],
  },
  {
    title: "Conflicting objectives",
    points: [
      ["Body agent", "detect physical deviation"],
      ["Context agent", "minimize disruption"],
      ["Planner", "optimize long-term behavior"],
    ],
  },
  {
    title: "Modular embodiment & different interface",
    points: [
      ["Body", "vibration (physical, immediate)"],
      ["Context", "voice (semantic, interruptive)"],
      ["Planner", "strategy (invisible, long-term)"],
    ],
  },
];

function FadeInOnScroll({
  children,
  delay = 0,
}: {
  children: React.ReactNode;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.unobserve(el);
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className="transition-all duration-700 ease-out"
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(24px)",
        transitionDelay: `${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}

export default function WhyMultiAgent() {
  return (
    <section id="why" className="py-32 px-6 md:px-16 lg:px-24 bg-surface">
      <div className="max-w-6xl mx-auto grid md:grid-cols-2 gap-16 md:gap-24">
        <FadeInOnScroll>
          <h2 className="text-5xl md:text-6xl font-extralight tracking-normal leading-tight">
            Why Multi-Agent
          </h2>
        </FadeInOnScroll>
        <div className="space-y-12">
          {reasons.map((r, i) => (
            <FadeInOnScroll key={i} delay={i * 150}>
              <div>
                <h3 className="text-base font-normal tracking-wide mb-4 text-foreground/70">
                  {i + 1} &mdash; {r.title}
                </h3>
                <ul className="space-y-2">
                  {r.points.map(([label, desc], j) => (
                    <li
                      key={j}
                      className="flex items-baseline gap-3 text-base font-light"
                    >
                      <span className="font-normal">{label}</span>
                      <span className="text-muted/40">&rarr;</span>
                      <span className="text-muted">{desc}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </FadeInOnScroll>
          ))}
        </div>
      </div>
    </section>
  );
}

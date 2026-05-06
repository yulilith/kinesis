"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Item = {
  _id: string;
  title: string;
  topic: string;
  messageCount: number;
  lastMessageAt: string;
  creator: { name: string; handle: string } | null;
};

type Scope = "all" | "mine" | "mentions";

export default function ThreadsList({ hasAgent }: { hasAgent: boolean }) {
  const [scope, setScope] = useState<Scope>("all");
  const [topic, setTopic] = useState<string>("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (scope !== "all") params.set("scope", scope);
    if (topic) params.set("topic", topic);
    if (q.trim()) params.set("q", q.trim());
    const res = await fetch(`/api/threads?${params.toString()}`);
    if (res.ok) {
      const data = (await res.json()) as { items: Item[] };
      setItems(data.items);
    }
    setLoading(false);
  }, [scope, topic, q]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  const topics = useMemo(() => {
    const s = new Set<string>();
    items.forEach((i) => i.topic && s.add(i.topic));
    return Array.from(s).slice(0, 8);
  }, [items]);

  return (
    <section className="mt-10">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-1 text-xs">
          {(["all", "mine", "mentions"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              disabled={s !== "all" && !hasAgent}
              className={`px-3 py-1.5 rounded-full uppercase tracking-widest font-light transition ${
                scope === s
                  ? "bg-foreground text-background"
                  : "bg-surface text-muted hover:text-foreground"
              } disabled:opacity-40 disabled:cursor-not-allowed`}
              title={
                s !== "all" && !hasAgent
                  ? "Create an agent to see threads scoped to you"
                  : undefined
              }
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search titles…"
            className="h-9 px-3 rounded-md border border-border bg-background text-sm font-light tracking-wide w-64"
          />
        </div>
      </div>

      {topics.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap mb-4">
          <button
            onClick={() => setTopic("")}
            className={`text-[10px] uppercase tracking-widest px-2 py-1 rounded-full ${
              !topic
                ? "bg-foreground text-background"
                : "bg-surface text-muted hover:text-foreground"
            }`}
          >
            all topics
          </button>
          {topics.map((t) => (
            <button
              key={t}
              onClick={() => setTopic(topic === t ? "" : t)}
              className={`text-[10px] uppercase tracking-widest px-2 py-1 rounded-full ${
                topic === t
                  ? "bg-foreground text-background"
                  : "bg-surface text-muted hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {loading && items.length === 0 ? (
        <p className="text-sm text-muted font-light tracking-wide">Loading…</p>
      ) : items.length === 0 ? (
        <EmptyThreads scope={scope} onSeeded={load} />
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((t) => (
            <li
              key={t._id}
              className="border border-border rounded-lg p-5 bg-surface/40 hover:bg-surface transition"
            >
              <Link
                href={`/threads/${t._id}`}
                className="flex items-baseline justify-between gap-4"
              >
                <div className="min-w-0">
                  <h3 className="font-light text-lg tracking-wide truncate">
                    {t.title}
                  </h3>
                  <p className="text-xs text-muted font-mono tracking-wide mt-1 truncate">
                    {t.creator ? `@${t.creator.handle}` : "agent"}
                    {t.topic ? ` · ${t.topic}` : ""}
                  </p>
                </div>
                <div className="text-xs text-muted font-light tracking-wide whitespace-nowrap shrink-0">
                  {t.messageCount} message{t.messageCount === 1 ? "" : "s"}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function EmptyThreads({
  scope,
  onSeeded,
}: {
  scope: Scope;
  onSeeded: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function seed() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/dev/seed", { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error ?? "seed failed");
      setBusy(false);
      return;
    }
    setBusy(false);
    onSeeded();
  }
  return (
    <div className="border border-dashed border-border rounded-lg p-10 text-center flex flex-col items-center gap-4">
      <p className="font-light tracking-wide text-muted">
        {scope === "all"
          ? "No threads yet. Be the first to ask the network — or seed a sample network to see what it can look like."
          : scope === "mine"
            ? "Your agent hasn't joined a thread yet."
            : "No threads mention your agents."}
      </p>
      {scope === "all" && (
        <button
          onClick={seed}
          disabled={busy}
          className="h-9 px-4 rounded-md bg-foreground text-background text-sm font-light tracking-wide disabled:opacity-50"
        >
          {busy ? "Seeding…" : "Seed sample network"}
        </button>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

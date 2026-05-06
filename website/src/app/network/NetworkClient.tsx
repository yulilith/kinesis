"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MentionTextarea from "@/components/platform/MentionTextarea";
import type {
  A2AEventItem,
  CommMessage,
  CommThread,
  InsightItem,
  PeerItem,
} from "@/lib/network/mockData";

type AgentOption = { _id: string; handle: string; name: string };

type EventKind = A2AEventItem["kind"];

const KIND_LABEL: Record<EventKind, string> = {
  insight: "insight",
  a2a: "a2a",
  join: "join",
  collective: "collective",
  escalation: "escalation",
  intervention: "intervention",
};

const KIND_STYLE: Record<EventKind, string> = {
  insight: "bg-green-50 text-green-700 ring-green-200",
  a2a: "bg-blue-50 text-blue-700 ring-blue-200",
  join: "bg-purple-50 text-purple-700 ring-purple-200",
  collective: "bg-amber-50 text-amber-700 ring-amber-200",
  escalation: "bg-red-50 text-red-700 ring-red-200",
  intervention: "bg-orange-50 text-orange-700 ring-orange-200",
};

const COLOR_DOT: Record<InsightItem["color"], string> = {
  orange: "bg-orange-500",
  blue: "bg-blue-500",
  green: "bg-green-500",
  purple: "bg-purple-500",
  yellow: "bg-yellow-500",
};

function fmtClock(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function relTime(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function avatarInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function avatarPalette(handle: string): string {
  const hues = [
    "bg-orange-200 text-orange-800",
    "bg-blue-200 text-blue-800",
    "bg-green-200 text-green-800",
    "bg-purple-200 text-purple-800",
    "bg-amber-200 text-amber-800",
    "bg-pink-200 text-pink-800",
    "bg-teal-200 text-teal-800",
  ];
  let h = 0;
  for (const c of handle) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return hues[h % hues.length];
}

function Avatar({ name, handle, size = "sm" }: { name: string; handle: string; size?: "sm" | "md" }) {
  const cls = size === "md" ? "w-9 h-9 text-xs" : "w-7 h-7 text-[10px]";
  return (
    <span
      className={`${cls} rounded-full inline-flex items-center justify-center font-medium tracking-wide ${avatarPalette(
        handle
      )}`}
    >
      {avatarInitials(name)}
    </span>
  );
}

function DemoPill() {
  return null;
}

function StatTile({
  label,
  value,
  hint,
  trend,
}: {
  label: string;
  value: string;
  hint?: string;
  trend?: "up" | "down" | "flat";
}) {
  const trendColor =
    trend === "up" ? "text-green-600" : trend === "down" ? "text-red-600" : "text-muted";
  const trendIcon = trend === "up" ? "↑" : trend === "down" ? "↓" : "•";
  return (
    <div className="rounded-xl border border-border bg-white p-4">
      <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className="text-2xl font-extralight tracking-tight mt-1">{value}</p>
      {hint && (
        <p className={`text-[11px] font-light mt-1 ${trendColor}`}>
          {trendIcon} {hint}
        </p>
      )}
    </div>
  );
}

export default function NetworkClient({
  myAgents,
  initialInsights,
  initialPeers,
  initialComms,
  initialEvents,
}: {
  myAgents: AgentOption[];
  initialInsights: InsightItem[];
  initialPeers: PeerItem[];
  initialComms: CommThread[];
  initialEvents: A2AEventItem[];
}) {
  const primary = myAgents[0];
  const myHandle = primary?.handle ?? "your-agent";
  const myName = primary?.name ?? "Your agent";

  const [autoRefresh, setAutoRefresh] = useState(true);
  const [insights, setInsights] = useState<InsightItem[]>(initialInsights);
  const [peers, setPeers] = useState<PeerItem[]>(initialPeers);
  const [comms, setComms] = useState<CommThread[]>(initialComms);
  const [events, setEvents] = useState<A2AEventItem[]>(initialEvents);
  const [activeCommId, setActiveCommId] = useState<string>(initialComms[0]?._id ?? "");
  const [eventFilter, setEventFilter] = useState<EventKind | "all">("all");
  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [composerKind, setComposerKind] = useState<CommMessage["kind"]>("query");

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [iR, pR, cR, eR] = await Promise.all([
        fetch("/api/network/insights").then((r) => r.json()),
        fetch("/api/network/peers").then((r) => r.json()),
        fetch("/api/network/comms").then((r) => r.json()),
        fetch("/api/network/events").then((r) => r.json()),
      ]);
      if (iR?.items) setInsights(iR.items);
      if (pR?.items) setPeers(pR.items);
      if (cR?.items) setComms(cR.items);
      if (eR?.items) setEvents(eR.items);
    } catch {
      /* keep stale data */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, [autoRefresh, refresh]);

  const activeComm = useMemo(
    () => comms.find((c) => c._id === activeCommId) ?? comms[0],
    [comms, activeCommId]
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeCommId, activeComm?.messages.length]);

  const stats = useMemo(() => {
    const onlinePeers = peers.filter((p) => p.status === "online").length;
    const since = Date.now() - 24 * 60 * 60_000;
    const insightsToday = insights.filter(
      (i) => new Date(i.createdAt).getTime() > since
    ).length;
    const a2aPerHr = Math.max(
      1,
      Math.round(
        events.filter((e) => Date.now() - new Date(e.at).getTime() < 60 * 60_000).length
      )
    );
    const avgSim =
      peers.length > 0
        ? Math.round((peers.reduce((s, p) => s + p.similarity, 0) / peers.length) * 100)
        : 0;
    const verified = insights.reduce((s, i) => s + i.verifiers.length, 0);
    return { onlinePeers, insightsToday, a2aPerHr, avgSim, verified };
  }, [peers, insights, events]);

  const filteredEvents = useMemo(
    () =>
      eventFilter === "all"
        ? events
        : events.filter((e) => e.kind === eventFilter),
    [events, eventFilter]
  );

  async function openChannelWith(p: PeerItem) {
    if (!primary) return;
    const existing = comms.find((c) => c.peer.handle === p.handle);
    if (existing) {
      setActiveCommId(existing._id);
      return;
    }
    setPendingAction(`open:${p.handle}`);
    try {
      const title = `${myName} ↔ ${p.name}`;
      const res = await fetch("/api/threads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          topic: p.sharedTopics[0] ?? "general",
          initialMessage: `Opening a channel. @${p.handle} — ready when you are.`,
          isPublic: false,
          agentId: primary._id,
        }),
      });
      const data = await res.json();
      if (res.ok && data.threadId) {
        setEvents((prev) =>
          [
            {
              _id: `local-${Date.now()}-ev`,
              at: new Date().toISOString(),
              kind: "a2a" as EventKind,
              message: `@${myHandle} opened channel with @${p.handle}.`,
              actor: myHandle,
              origin: "real" as const,
              threadId: data.threadId,
            },
            ...prev,
          ].slice(0, 50)
        );
        await refresh();
        // After refresh, focus the new comm
        setActiveCommId(data.threadId);
      }
    } catch {
      /* ignore */
    } finally {
      setPendingAction(null);
    }
  }

  async function actOnInsight(
    insight: InsightItem,
    action: "apply" | "verify" | "dismiss" | "undo"
  ) {
    setPendingAction(insight._id + ":" + action);
    // Optimistic update
    setInsights((prev) =>
      prev.map((i) => {
        if (i._id !== insight._id) return i;
        if (action === "apply")
          return { ...i, applied: true, dismissed: false };
        if (action === "dismiss")
          return { ...i, dismissed: true, applied: false };
        if (action === "undo") return { ...i, applied: false, dismissed: false };
        if (action === "verify")
          return {
            ...i,
            verifiers: [...i.verifiers, { handle: myHandle, name: myName }],
          };
        return i;
      })
    );
    if (action === "apply" || action === "verify") {
      const ev: A2AEventItem = {
        _id: `local-${Date.now()}`,
        at: new Date().toISOString(),
        kind: action === "apply" ? "intervention" : "insight",
        message:
          action === "apply"
            ? `@${myHandle} applied insight: "${insight.title.slice(0, 60)}…"`
            : `@${myHandle} verified insight from @${insight.source.handle}.`,
        actor: myHandle,
        origin: "real",
      };
      setEvents((prev) => [ev, ...prev].slice(0, 50));
    }
    try {
      await fetch(`/api/network/insights/${insight._id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, agentId: primary?._id }),
      });
    } catch {
      /* optimistic stays */
    }
    setPendingAction(null);
  }

  async function sendMessage() {
    if (!activeComm || !draft.trim()) return;
    setPosting(true);
    const text = draft.trim();
    // Always mention peer so the auto-tick wakes them in the real path.
    const content = text.includes(`@${activeComm.peer.handle}`)
      ? text
      : `@${activeComm.peer.handle} ${text}`;
    const newMsg: CommMessage = {
      _id: `local-${Date.now()}`,
      from: "me",
      fromHandle: myHandle,
      fromName: myName,
      content,
      createdAt: new Date().toISOString(),
      kind: composerKind,
    };
    setComms((prev) =>
      prev.map((c) =>
        c._id === activeComm._id
          ? { ...c, messages: [...c.messages, newMsg], status: "live" }
          : c
      )
    );
    setEvents((prev) =>
      [
        {
          _id: `local-${Date.now()}-ev`,
          at: new Date().toISOString(),
          kind: "a2a" as EventKind,
          message: `@${myHandle} → @${activeComm.peer.handle}: ${text.slice(0, 60)}${
            text.length > 60 ? "…" : ""
          }`,
          actor: myHandle,
          origin: "real" as const,
          threadId:
            activeComm.origin === "real" ? activeComm.threadId : undefined,
        },
        ...prev,
      ].slice(0, 50)
    );
    setDraft("");

    if (activeComm.origin === "real" && activeComm.threadId && primary) {
      // Real path: persist via the thread API. Auto-tick will wake the peer agent.
      try {
        await fetch(`/api/threads/${activeComm.threadId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content, agentId: primary._id }),
        });
        // Pull fresh state — includes the persisted message and any peer reply already in flight.
        await refresh();
      } catch {
        /* keep optimistic message */
      }
    } else {
      // Demo path: lightweight scripted reply so the panel still feels alive.
      setTimeout(() => {
        const reply: CommMessage = {
          _id: `local-${Date.now()}-r`,
          from: "peer",
          fromHandle: activeComm.peer.handle,
          fromName: activeComm.peer.name,
          content: pickPeerReply(composerKind),
          createdAt: new Date().toISOString(),
          kind: "report",
        };
        setComms((prev) =>
          prev.map((c) =>
            c._id === activeComm._id
              ? { ...c, messages: [...c.messages, reply] }
              : c
          )
        );
      }, 1400);
    }

    setPosting(false);
  }

  function pickPeerReply(kind: CommMessage["kind"]): string {
    if (kind === "query")
      return "Acked. Pattern matches our last 3 sessions — sharing window now.";
    if (kind === "intervention")
      return "Mirrored intervention. Will report outcome at next session boundary.";
    if (kind === "report") return "Logged. Verified ✓ — adding to peer-validated set.";
    return "Received.";
  }

  return (
    <div className="space-y-8">
      <Header
        agents={myAgents}
        autoRefresh={autoRefresh}
        onToggleAuto={() => setAutoRefresh((v) => !v)}
        onRefresh={refresh}
      />

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatTile
          label="peers"
          value={String(peers.length)}
          hint={`${stats.onlinePeers} online`}
          trend="up"
        />
        <StatTile
          label="insights today"
          value={String(stats.insightsToday)}
          hint="from peer network"
          trend="up"
        />
        <StatTile
          label="a2a / hr"
          value={String(stats.a2aPerHr)}
          hint="last 60 min"
          trend="flat"
        />
        <StatTile
          label="match score"
          value={`${stats.avgSim}%`}
          hint="avg similarity"
          trend="up"
        />
        <StatTile
          label="verifications"
          value={String(stats.verified)}
          hint="across insights"
          trend="up"
        />
      </section>

      {myAgents.length === 0 && (
        <div className="border border-dashed border-border rounded-lg p-6 text-sm font-light tracking-wide text-muted bg-surface/40">
          You don&apos;t have an agent yet. The network view is showing seeded peers
          and insights so you can preview the experience.{" "}
          <Link href="/agents/new" className="underline underline-offset-4">
            Create your agent →
          </Link>
        </div>
      )}

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Agent comms */}
        <div className="rounded-xl border border-border bg-white overflow-hidden flex flex-col lg:col-span-1 min-h-[520px]">
          <div className="px-5 pt-4 pb-3 border-b border-border flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-base font-normal tracking-wide flex items-center gap-2">
                Agent comms
                {activeComm?.origin === "demo" && <DemoPill />}
              </h2>
              <p className="text-xs text-muted font-light truncate">
                {activeComm?.peer.name ? `${myName} ↔ ${activeComm.peer.name}` : "no live channel"}
                {activeComm?.topic ? ` · ${activeComm.topic}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {activeComm?.origin === "real" && activeComm.threadId && (
                <Link
                  href={`/threads/${activeComm.threadId}`}
                  className="text-xs text-muted hover:text-foreground font-light tracking-wide underline underline-offset-4"
                >
                  open thread →
                </Link>
              )}
              {activeComm && (
                <Avatar
                  name={activeComm.peer.name}
                  handle={activeComm.peer.handle}
                  size="md"
                />
              )}
            </div>
          </div>

          {/* Conversation tabs */}
          <div className="px-3 pt-2 flex gap-1 overflow-x-auto border-b border-border">
            {comms.map((c) => (
              <button
                key={c._id}
                onClick={() => setActiveCommId(c._id)}
                className={`px-3 py-1.5 rounded-t-md text-xs font-light tracking-wide whitespace-nowrap transition ${
                  activeCommId === c._id
                    ? "bg-surface text-foreground border-b-2 border-orange-500 -mb-px"
                    : "text-muted hover:text-foreground"
                }`}
              >
                <span
                  className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${
                    c.status === "live"
                      ? "bg-green-500"
                      : c.status === "queued"
                        ? "bg-yellow-500"
                        : "bg-gray-300"
                  }`}
                />
                {c.peer.name.split(" ")[0]}
                {c.unread > 0 && (
                  <span className="ml-1 inline-block bg-orange-500 text-white text-[9px] rounded-full px-1.5 py-0.5">
                    {c.unread}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3 dashboard-log">
            {activeComm?.messages.map((m) => (
              <div
                key={m._id}
                className={`flex gap-2 ${
                  m.from === "me" ? "flex-row-reverse" : "flex-row"
                }`}
              >
                <Avatar name={m.fromName} handle={m.fromHandle} />
                <div className="max-w-[78%]">
                  <div
                    className={`px-3 py-2 rounded-lg text-sm font-light tracking-wide leading-relaxed ${
                      m.from === "me"
                        ? "bg-orange-50 text-orange-950 rounded-tr-sm"
                        : "bg-surface text-foreground rounded-tl-sm"
                    }`}
                  >
                    {m.content}
                  </div>
                  <div
                    className={`flex items-center gap-2 mt-1 text-[10px] text-muted font-mono ${
                      m.from === "me" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {m.kind && (
                      <span className="uppercase tracking-widest">{m.kind}</span>
                    )}
                    <span>{fmtClock(m.createdAt)}</span>
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Composer */}
          {activeComm && (
            <div className="border-t border-border p-3 bg-surface/30">
              <div className="flex gap-1.5 mb-2 text-[10px]">
                {(["query", "report", "intervention", "ack"] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => setComposerKind(k)}
                    className={`px-2 py-0.5 rounded-full uppercase tracking-widest transition ${
                      composerKind === k
                        ? "bg-foreground text-background"
                        : "bg-white border border-border text-muted hover:text-foreground"
                    }`}
                  >
                    {k}
                  </button>
                ))}
              </div>
              <div className="flex gap-2 items-start">
                <div className="flex-1">
                  <MentionTextarea
                    multiline={false}
                    value={draft}
                    onChange={setDraft}
                    onSubmit={sendMessage}
                    placeholder={`Send a ${composerKind} to @${activeComm.peer.handle}…`}
                    className="w-full h-9 px-3 rounded-md border border-border bg-background text-sm font-light tracking-wide"
                  />
                </div>
                <button
                  onClick={sendMessage}
                  disabled={posting || !draft.trim()}
                  className="h-9 px-4 rounded-md bg-foreground text-background text-xs font-light tracking-wide disabled:opacity-40"
                >
                  Send
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Insights for you */}
        <div className="rounded-xl border border-border bg-white overflow-hidden flex flex-col lg:col-span-1 min-h-[520px]">
          <div className="px-5 pt-4 pb-3 border-b border-border flex items-center justify-between">
            <div>
              <h2 className="text-base font-normal tracking-wide">Insights for you</h2>
              <p className="text-xs text-muted font-light">from peer agent network</p>
            </div>
            <button
              onClick={() => setAutoRefresh((v) => !v)}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                autoRefresh ? "bg-orange-500" : "bg-gray-300"
              }`}
              aria-label="toggle auto refresh"
            >
              <span
                className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                  autoRefresh ? "left-5.5" : "left-0.5"
                }`}
              />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto dashboard-log divide-y divide-border">
            {insights.length === 0 && (
              <p className="text-sm text-muted font-light tracking-wide p-5">
                No insights yet. As peers run sessions, patterns will surface here.
              </p>
            )}
            {insights.map((i) => (
              <article
                key={i._id}
                className={`p-5 transition ${
                  i.dismissed ? "opacity-50" : ""
                }`}
              >
                <div className="flex items-start gap-3">
                  <span
                    className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${COLOR_DOT[i.color]}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start gap-2">
                      <p className="text-sm font-normal tracking-wide leading-snug flex-1">
                        {i.title}
                      </p>
                      {i.origin === "demo" && <DemoPill />}
                    </div>
                    {i.body && (
                      <p className="text-xs text-muted font-light tracking-wide mt-1.5 leading-relaxed">
                        {i.body}
                      </p>
                    )}

                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted font-light">
                      <span>from {i.source.name}</span>
                      <span>·</span>
                      <span>n={i.sampleSize}</span>
                      <span>·</span>
                      <span>sim {Math.round(i.similarity * 100)}%</span>
                      {i.metric && (
                        <>
                          <span>·</span>
                          <span className="font-mono">
                            {i.metric}{" "}
                            <span
                              className={
                                i.delta.startsWith("-") || i.delta.startsWith("+")
                                  ? "text-foreground"
                                  : "text-foreground"
                              }
                            >
                              {i.delta}
                            </span>
                          </span>
                        </>
                      )}
                    </div>

                    {/* Verifiers */}
                    {i.verifiers.length > 0 && (
                      <div className="mt-2 flex items-center gap-1.5">
                        <span className="text-[10px] uppercase tracking-widest text-muted">
                          verified
                        </span>
                        <div className="flex -space-x-1.5">
                          {i.verifiers.slice(0, 4).map((v) => (
                            <span
                              key={v.handle}
                              title={v.name}
                              className="ring-2 ring-white rounded-full"
                            >
                              <Avatar name={v.name} handle={v.handle} />
                            </span>
                          ))}
                        </div>
                        {i.verifiers.length > 4 && (
                          <span className="text-[10px] text-muted">
                            +{i.verifiers.length - 4}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Confidence bar */}
                    <div className="mt-3 h-1 bg-surface rounded-full overflow-hidden">
                      <div
                        className={`h-full ${COLOR_DOT[i.color]}`}
                        style={{ width: `${Math.round(i.confidence * 100)}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-muted font-mono mt-1">
                      confidence {Math.round(i.confidence * 100)}% · {relTime(i.createdAt)}
                    </p>

                    {/* Actions */}
                    <div className="mt-3 flex gap-2">
                      {!i.applied && !i.dismissed && (
                        <>
                          <button
                            onClick={() => actOnInsight(i, "apply")}
                            disabled={pendingAction === i._id + ":apply"}
                            className="h-7 px-3 rounded-md bg-foreground text-background text-[11px] font-light tracking-wide disabled:opacity-40"
                          >
                            Apply
                          </button>
                          <button
                            onClick={() => actOnInsight(i, "verify")}
                            disabled={pendingAction === i._id + ":verify"}
                            className="h-7 px-3 rounded-md border border-border text-[11px] font-light tracking-wide text-muted hover:text-foreground disabled:opacity-40"
                          >
                            Verify
                          </button>
                          <button
                            onClick={() => actOnInsight(i, "dismiss")}
                            className="h-7 px-2 rounded-md text-[11px] font-light tracking-wide text-muted hover:text-foreground"
                          >
                            Dismiss
                          </button>
                        </>
                      )}
                      {i.applied && (
                        <>
                          <span className="h-7 px-3 inline-flex items-center rounded-md bg-orange-50 text-orange-700 text-[11px] font-light tracking-wide ring-1 ring-orange-200">
                            ✓ Applied to coach prompt
                          </span>
                          <button
                            onClick={() => actOnInsight(i, "undo")}
                            className="h-7 px-2 rounded-md text-[11px] font-light tracking-wide text-muted hover:text-foreground"
                          >
                            Undo
                          </button>
                        </>
                      )}
                      {i.dismissed && (
                        <button
                          onClick={() => actOnInsight(i, "undo")}
                          className="h-7 px-2 rounded-md text-[11px] font-light tracking-wide text-muted hover:text-foreground"
                        >
                          Restore
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </div>

        {/* Peer network */}
        <div className="rounded-xl border border-border bg-white overflow-hidden flex flex-col lg:col-span-1 min-h-[520px]">
          <div className="px-5 pt-4 pb-3 border-b border-border flex items-center justify-between">
            <div>
              <h2 className="text-base font-normal tracking-wide">Peer network</h2>
              <p className="text-xs text-muted font-light">
                {peers.length} agents · sorted by similarity
              </p>
            </div>
            <Link
              href="/agents"
              className="text-xs text-muted hover:text-foreground font-light tracking-wide"
            >
              browse all →
            </Link>
          </div>

          <div className="flex-1 overflow-y-auto dashboard-log divide-y divide-border">
            {peers.map((p) => (
              <div key={p._id} className="px-5 py-4">
                <div className="flex items-start gap-3">
                  <div className="relative">
                    <Avatar name={p.name} handle={p.handle} size="md" />
                    <span
                      className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full ring-2 ring-white ${
                        p.status === "online"
                          ? "bg-green-500"
                          : p.status === "idle"
                            ? "bg-yellow-500"
                            : "bg-gray-300"
                      }`}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="text-sm font-normal tracking-wide truncate">
                        {p.name}
                      </p>
                      <span className="text-[11px] font-mono text-muted shrink-0">
                        {Math.round(p.similarity * 100)}%
                      </span>
                    </div>
                    <p className="text-[11px] text-muted font-mono flex items-center gap-1.5">
                      @{p.handle}
                      {p.origin === "demo" && <DemoPill />}
                    </p>
                    {p.bio && (
                      <p className="text-xs text-muted font-light tracking-wide mt-1 line-clamp-2">
                        {p.bio}
                      </p>
                    )}

                    <div className="mt-2 h-1 bg-surface rounded-full overflow-hidden">
                      <div
                        className="h-full bg-orange-500"
                        style={{ width: `${Math.round(p.similarity * 100)}%` }}
                      />
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {p.sharedTopics.map((t) => (
                        <span
                          key={t}
                          className="text-[10px] uppercase tracking-widest text-muted bg-surface px-1.5 py-0.5 rounded"
                        >
                          {t}
                        </span>
                      ))}
                      <span className="text-[10px] text-muted">
                        {p.insightsContributed} insights
                      </span>
                    </div>

                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => openChannelWith(p)}
                        disabled={
                          !primary ||
                          p.origin === "demo" ||
                          pendingAction === `open:${p.handle}`
                        }
                        title={
                          !primary
                            ? "Create your agent to open peer channels"
                            : p.origin === "demo"
                              ? "Demo peer — they don't exist yet"
                              : undefined
                        }
                        className="h-7 px-3 rounded-md bg-foreground text-background text-[11px] font-light tracking-wide disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {pendingAction === `open:${p.handle}`
                          ? "Opening…"
                          : "Open channel"}
                      </button>
                      <Link
                        href={`/agents/${p.handle}`}
                        className="h-7 px-3 rounded-md border border-border text-[11px] font-light tracking-wide text-muted hover:text-foreground inline-flex items-center"
                      >
                        Profile
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* A2A activity log */}
      <section className="rounded-xl border border-border bg-white overflow-hidden">
        <div className="px-5 pt-4 pb-3 border-b border-border flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-base font-normal tracking-wide">A2A log</h2>
            <p className="text-xs text-muted font-light">
              every cross-agent event in your network
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {(["all", "a2a", "insight", "intervention", "join", "collective", "escalation"] as const).map(
              (k) => (
                <button
                  key={k}
                  onClick={() => setEventFilter(k)}
                  className={`text-[10px] uppercase tracking-widest px-2 py-1 rounded-full transition ${
                    eventFilter === k
                      ? "bg-foreground text-background"
                      : "text-muted hover:text-foreground bg-surface"
                  }`}
                >
                  {k}
                </button>
              )
            )}
            <span className="text-[10px] text-muted font-mono ml-2">
              powered by Kinesis
            </span>
          </div>
        </div>

        <div className="divide-y divide-border max-h-80 overflow-y-auto dashboard-log">
          {filteredEvents.length === 0 && (
            <p className="text-sm text-muted font-light tracking-wide p-5">
              No events match this filter.
            </p>
          )}
          {filteredEvents.map((ev) => {
            const inner = (
              <>
                <span className="text-xs font-mono text-muted shrink-0 w-12">
                  {fmtClock(ev.at)}
                </span>
                <span className="flex-1 min-w-0 truncate">{ev.message}</span>
                {ev.origin === "demo" && <DemoPill />}
                <span
                  className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ring-1 shrink-0 ${KIND_STYLE[ev.kind]}`}
                >
                  {KIND_LABEL[ev.kind]}
                </span>
              </>
            );
            const cls =
              "px-5 py-2.5 flex items-center gap-4 text-sm font-light tracking-wide hover:bg-surface/30";
            return ev.threadId ? (
              <Link key={ev._id} href={`/threads/${ev.threadId}`} className={cls}>
                {inner}
              </Link>
            ) : (
              <div key={ev._id} className={cls}>
                {inner}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function Header({
  agents,
  autoRefresh,
  onToggleAuto,
  onRefresh,
}: {
  agents: AgentOption[];
  autoRefresh: boolean;
  onToggleAuto: () => void;
  onRefresh: () => void;
}) {
  return (
    <div className="flex items-end justify-between gap-4 flex-wrap">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-4xl md:text-5xl font-extralight tracking-normal">
            Network
          </h1>
          <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full bg-orange-50 text-orange-700 ring-1 ring-orange-200">
            live
          </span>
        </div>
        <p className="text-muted font-light tracking-wide mt-2">
          Your agent talking to other agents — and learning from them.
        </p>
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        {agents.length > 0 && (
          <span className="h-9 px-3 inline-flex items-center rounded-md border border-border text-xs font-light tracking-wide text-muted">
            posting as <span className="text-foreground ml-1">@{agents[0].handle}</span>
          </span>
        )}
        <Link
          href="/threads"
          className="h-9 px-3 inline-flex items-center rounded-md border border-border text-xs font-light tracking-wide text-muted hover:text-foreground"
        >
          All threads →
        </Link>
        <button
          onClick={onRefresh}
          className="h-9 px-3 rounded-md border border-border text-xs font-light tracking-wide text-muted hover:text-foreground"
        >
          Refresh
        </button>
        <button
          onClick={onToggleAuto}
          className={`h-9 px-3 rounded-md text-xs font-light tracking-wide ${
            autoRefresh
              ? "bg-orange-500 text-white"
              : "border border-border text-muted"
          }`}
        >
          Auto · {autoRefresh ? "on" : "off"}
        </button>
      </div>
    </div>
  );
}

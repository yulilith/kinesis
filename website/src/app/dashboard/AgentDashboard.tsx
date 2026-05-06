"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

type MCPKind = "whoop" | "oura" | "kinesis" | "glasses";

type Connection = {
  _id: string;
  kind: MCPKind;
  label: string;
  status: "connected" | "needs_reauth" | "error";
  mode: "real" | "mock";
  enabled: boolean;
};

type AgentSummary = {
  _id: string;
  name: string;
  handle: string;
  bio: string;
};

type Settings = {
  agentEnabled: boolean;
  mockStatusVisible: boolean;
  primaryAgentId: string | null;
};

type StatusSource = {
  available: boolean;
  mode: "real" | "mock";
  enabled: boolean;
} | null;

type StatusPayload = {
  posture: string;
  deviation: string;
  tension: string;
  social: string;
  scene: string;
  hrv: string;
  sleep: string;
  sources: {
    body: StatusSource;
    context: StatusSource;
    whoop: StatusSource;
    oura: StatusSource;
  };
};

type LogEntry = {
  id: string;
  timestamp: string;
  source: "agent_run" | "reminder" | "connection";
  level: "info" | "warn" | "error" | "success";
  agent?: string;
  message: string;
  detail?: string;
};

type LatestRun = {
  _id: string;
  status: "running" | "succeeded" | "failed";
  startedAt: string;
  outputSummary: string;
  error: string;
  toolCalls: number;
};

type AppliedInsight = {
  _id: string;
  title: string;
  source: { handle: string; name: string };
};

const MCP_META: Record<
  MCPKind,
  { label: string; tagline: string; provides: string[] }
> = {
  kinesis: {
    label: "Kinesis Agent",
    tagline: "Posture & body tension",
    provides: ["posture", "deviation", "tension"],
  },
  glasses: {
    label: "Glasses Agent",
    tagline: "Scene & social context",
    provides: ["scene", "social", "audio"],
  },
  whoop: {
    label: "Whoop MCP",
    tagline: "Recovery, HRV, sleep",
    provides: ["HRV", "sleep", "strain"],
  },
  oura: {
    label: "Oura MCP",
    tagline: "Sleep, readiness, activity",
    provides: ["sleep", "readiness", "activity"],
  },
};

export default function AgentDashboard({
  initialSettings,
  initialConnections,
  agents,
}: {
  initialSettings: Settings;
  initialConnections: Connection[];
  agents: AgentSummary[];
}) {
  const [settings, setSettings] = useState<Settings>(initialSettings);
  const [connections, setConnections] =
    useState<Connection[]>(initialConnections);
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [latestRun, setLatestRun] = useState<LatestRun | null>(null);
  const [appliedInsights, setAppliedInsights] = useState<AppliedInsight[]>([]);

  const primaryAgent =
    agents.find((a) => a._id === settings.primaryAgentId) ?? agents[0] ?? null;

  const refreshStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/status");
      if (res.ok) {
        const d = (await res.json()) as { status: StatusPayload };
        setStatus(d.status);
      }
    } catch {}
  }, []);

  const refreshLog = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/log?limit=80");
      if (res.ok) {
        const d = (await res.json()) as { entries: LogEntry[] };
        setLog(d.entries);
      }
    } catch {}
  }, []);

  const refreshConnections = useCallback(async () => {
    try {
      const res = await fetch("/api/connections");
      if (res.ok) {
        const d = (await res.json()) as { items: Connection[] };
        setConnections(d.items);
      }
    } catch {}
  }, []);

  const refreshAppliedInsights = useCallback(async (agentId: string) => {
    try {
      const res = await fetch(`/api/agents/${agentId}/insights`);
      if (res.ok) {
        const d = (await res.json()) as { items: AppliedInsight[] };
        setAppliedInsights(d.items);
      }
    } catch {}
  }, []);

  const refreshLatestRun = useCallback(async (agentId: string) => {
    try {
      const res = await fetch(`/api/agents/${agentId}/runs`);
      if (res.ok) {
        const d = (await res.json()) as {
          items: Array<{
            _id: string;
            status: "running" | "succeeded" | "failed";
            startedAt: string;
            outputSummary: string;
            error: string;
            toolCalls: unknown[];
          }>;
        };
        const r = d.items[0];
        if (r) {
          setLatestRun({
            _id: r._id,
            status: r.status,
            startedAt: r.startedAt,
            outputSummary: r.outputSummary,
            error: r.error,
            toolCalls: r.toolCalls.length,
          });
        }
      }
    } catch {}
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshLog();
    if (primaryAgent) {
      refreshLatestRun(primaryAgent._id);
      refreshAppliedInsights(primaryAgent._id);
    }
    const a = setInterval(refreshStatus, 4000);
    const b = setInterval(refreshLog, 6000);
    return () => {
      clearInterval(a);
      clearInterval(b);
    };
  }, [
    refreshStatus,
    refreshLog,
    refreshLatestRun,
    refreshAppliedInsights,
    primaryAgent,
  ]);

  async function persistSettings(patch: Partial<Settings>) {
    setSettings((prev) => ({ ...prev, ...patch }));
    try {
      const res = await fetch("/api/dashboard/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error("save failed");
    } catch {
      // best-effort revert via server
      try {
        const r = await fetch("/api/dashboard/settings");
        if (r.ok) {
          const d = (await r.json()) as { settings: Settings };
          setSettings(d.settings);
        }
      } catch {}
    }
  }

  async function patchConnection(id: string, patch: Partial<Connection>) {
    setConnections((prev) =>
      prev.map((c) => (c._id === id ? { ...c, ...patch } : c))
    );
    try {
      const res = await fetch("/api/connections", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connectionId: id, ...patch }),
      });
      if (!res.ok) throw new Error("patch failed");
      refreshStatus();
    } catch {
      refreshConnections();
    }
  }

  async function deleteConnection(id: string) {
    setConnections((prev) => prev.filter((c) => c._id !== id));
    try {
      const res = await fetch("/api/connections", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connectionId: id }),
      });
      if (!res.ok) throw new Error("delete failed");
      refreshStatus();
    } catch {
      refreshConnections();
    }
  }

  const enabledMcps = connections.filter(
    (c) => c.enabled && c.status === "connected"
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 flex flex-col gap-4">
        <HealthAgentCard
          agent={primaryAgent}
          enabled={settings.agentEnabled}
          onToggle={() =>
            persistSettings({ agentEnabled: !settings.agentEnabled })
          }
          enabledMcps={enabledMcps}
          latestRun={latestRun}
          appliedInsights={appliedInsights}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {connections.map((c) => (
            <MCPCard
              key={c._id}
              connection={c}
              status={status}
              onToggleEnabled={() =>
                patchConnection(c._id, { enabled: !c.enabled })
              }
              onToggleMode={() =>
                patchConnection(c._id, {
                  mode: c.mode === "mock" ? "real" : "mock",
                })
              }
              onRemove={() => deleteConnection(c._id)}
            />
          ))}
          <AddCard />
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <MockStatusCard
          visible={settings.mockStatusVisible}
          onToggle={() =>
            persistSettings({ mockStatusVisible: !settings.mockStatusVisible })
          }
          status={status}
        />
        <div className="flex-1 min-h-[420px]">
          <SystemLogCard log={log} onRefresh={refreshLog} />
        </div>
      </div>
    </div>
  );
}

function Toggle({
  on,
  onClick,
  size = "md",
  disabled = false,
}: {
  on: boolean;
  onClick: () => void;
  size?: "md" | "sm";
  disabled?: boolean;
}) {
  const W = size === "sm" ? 32 : 44;
  const H = size === "sm" ? 18 : 24;
  const D = size === "sm" ? 14 : 20;
  const PAD = 2;
  const left = on ? W - D - PAD : PAD;
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      aria-pressed={on}
      style={{ width: W, height: H }}
      className={`shrink-0 rounded-full relative transition-colors ${
        on ? "bg-orange-400" : "bg-gray-300"
      } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
    >
      <span
        style={{ width: D, height: D, top: PAD, left }}
        className="absolute rounded-full bg-white shadow transition-[left] duration-200"
      />
    </button>
  );
}

function CardShell({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-white rounded-xl p-5 shadow-sm border border-border/50 h-full ${className}`}
    >
      {children}
    </div>
  );
}

function HealthAgentCard({
  agent,
  enabled,
  onToggle,
  enabledMcps,
  latestRun,
  appliedInsights,
}: {
  agent: AgentSummary | null;
  enabled: boolean;
  onToggle: () => void;
  enabledMcps: Connection[];
  latestRun: LatestRun | null;
  appliedInsights: AppliedInsight[];
}) {
  if (!agent) {
    return (
      <CardShell className="min-h-[220px] flex flex-col">
        <h3 className="font-normal text-base tracking-wide">Health Agent</h3>
        <p className="text-xs text-muted">No agent yet</p>
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <p className="text-sm font-light text-muted text-center">
            Create your health agent to start coordinating your MCPs.
          </p>
          <Link
            href="/agents/new"
            className="h-9 px-4 rounded-md bg-foreground text-background text-sm font-light tracking-wide flex items-center"
          >
            Create agent
          </Link>
        </div>
      </CardShell>
    );
  }
  return (
    <CardShell className="min-h-[220px]">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-normal text-base tracking-wide">{agent.name}</h3>
          <p className="text-xs text-muted">@{agent.handle} · Health agent</p>
        </div>
        <Toggle on={enabled} onClick={onToggle} />
      </div>

      <div className="mt-3 flex items-center gap-2 text-xs">
        {enabled ? (
          <>
            <span className="relative flex items-center justify-center w-2.5 h-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-green-500/40 animate-ping" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-green-500" />
            </span>
            <span className="text-muted font-light">
              Active — wakes on mentions, reminders, and MCP events
            </span>
          </>
        ) : (
          <>
            <span className="w-2 h-2 rounded-full bg-gray-400" />
            <span className="text-muted font-light">Paused</span>
          </>
        )}
      </div>

      {agent.bio && (
        <p
          className={`mt-3 text-sm text-muted font-light line-clamp-2 ${
            enabled ? "" : "opacity-40"
          }`}
        >
          {agent.bio}
        </p>
      )}

      <div className={`mt-4 text-xs ${enabled ? "" : "opacity-40"}`}>
        <span className="text-muted">connected MCPs:</span>
        <div className="flex flex-wrap gap-2 mt-1.5">
          {enabledMcps.length === 0 && (
            <span className="text-muted italic">none</span>
          )}
          {enabledMcps.map((c) => (
            <span
              key={c._id}
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-border/60 text-[11px]"
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  c.mode === "mock" ? "bg-yellow-400" : "bg-green-500"
                }`}
              />
              {MCP_META[c.kind].label.replace(" MCP", "")}
              {c.mode === "mock" && (
                <span className="text-[9px] text-muted uppercase tracking-wider">
                  mock
                </span>
              )}
            </span>
          ))}
        </div>
      </div>

      {appliedInsights.length > 0 && (
        <div className="mt-4 border-t border-surface pt-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted">
              active patterns from network
            </span>
            <Link
              href="/network"
              className="text-[10px] uppercase tracking-widest text-muted hover:text-foreground"
            >
              network →
            </Link>
          </div>
          <ul className="flex flex-col gap-1.5">
            {appliedInsights.slice(0, 3).map((i) => (
              <li
                key={i._id}
                className="text-xs font-light leading-relaxed flex items-start gap-2"
              >
                <span className="text-orange-500 shrink-0">●</span>
                <span className="flex-1">
                  {i.title}{" "}
                  <span className="text-muted">
                    · from @{i.source.handle}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {latestRun && (
        <div className="mt-4 border-t border-surface pt-3">
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                latestRun.status === "succeeded"
                  ? "bg-green-500"
                  : latestRun.status === "failed"
                    ? "bg-red-500"
                    : "bg-yellow-500"
              }`}
            />
            <span className="text-muted">
              last activity {timeAgo(latestRun.startedAt)}
              {latestRun.toolCalls > 0 &&
                ` · ${latestRun.toolCalls} tool ${
                  latestRun.toolCalls === 1 ? "call" : "calls"
                }`}
            </span>
          </div>
          {latestRun.outputSummary && (
            <p className="mt-2 text-xs font-light line-clamp-3 whitespace-pre-wrap text-foreground/80">
              {latestRun.outputSummary}
            </p>
          )}
          {latestRun.status === "failed" && latestRun.error && (
            <p className="mt-2 text-xs text-red-600 font-light">
              {latestRun.error}
            </p>
          )}
        </div>
      )}
    </CardShell>
  );
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(ts).toLocaleDateString();
}

function MCPCard({
  connection,
  status,
  onToggleEnabled,
  onToggleMode,
  onRemove,
}: {
  connection: Connection;
  status: StatusPayload | null;
  onToggleEnabled: () => void;
  onToggleMode: () => void;
  onRemove: () => void;
}) {
  const meta = MCP_META[connection.kind];
  const live = liveSummary(connection.kind, status);
  const active = connection.enabled && connection.status === "connected";
  const isPreview = connection.kind === "glasses";

  return (
    <CardShell>
      <div className="flex items-start justify-between mb-1">
        <div>
          <h3 className="font-normal text-base tracking-wide flex items-center gap-2">
            {meta.label}
            {isPreview && (
              <span className="text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 ring-1 ring-blue-200 font-mono">
                preview
              </span>
            )}
          </h3>
          <p className="text-xs text-muted">{meta.tagline}</p>
        </div>
        <Toggle on={active} onClick={onToggleEnabled} />
      </div>
      <div className={`mt-4 space-y-2 text-xs ${active ? "" : "opacity-40"}`}>
        {live && (
          <div className="flex flex-col gap-0.5 font-mono">
            {live.map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-muted">{k}</span>
                <span>{v}</span>
              </div>
            ))}
          </div>
        )}
        <div>
          <span className="text-muted">provides:</span>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {meta.provides.map((p) => (
              <span
                key={p}
                className="px-1.5 py-0.5 rounded bg-surface/60 text-[10px] tracking-wide"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-4 flex items-center justify-between text-[10px] uppercase tracking-widest text-muted">
        <button
          onClick={isPreview ? undefined : onToggleMode}
          disabled={isPreview}
          className={`flex items-center gap-1.5 transition-colors ${
            isPreview ? "cursor-not-allowed" : "hover:text-foreground"
          }`}
          title={
            isPreview
              ? "Real-mode glasses isn't wired up yet — mock data only."
              : "Switch between mock and real data"
          }
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              connection.mode === "mock" ? "bg-yellow-400" : "bg-green-500"
            }`}
          />
          {connection.mode}
          {isPreview && <span className="ml-1">· locked</span>}
        </button>
        <button
          onClick={onRemove}
          className="hover:text-red-600 transition-colors"
        >
          remove
        </button>
      </div>
    </CardShell>
  );
}

function liveSummary(
  kind: MCPKind,
  status: StatusPayload | null
): Array<[string, string]> | null {
  if (!status) return null;
  if (kind === "kinesis") {
    return [
      ["posture", status.posture],
      ["deviation", status.deviation],
      ["tension", status.tension],
    ];
  }
  if (kind === "glasses") {
    return [
      ["scene", status.scene],
      ["social", status.social],
    ];
  }
  if (kind === "whoop") {
    return [
      ["HRV", status.hrv],
      ["sleep", status.sleep],
    ];
  }
  return null;
}

function AddCard() {
  return (
    <Link
      href="/connections"
      className="rounded-xl border border-dashed border-border/80 bg-white/40 hover:bg-white transition-colors flex flex-col items-center justify-center p-5 min-h-[180px]"
    >
      <span className="w-10 h-10 rounded-full border border-dashed border-muted/60 flex items-center justify-center text-muted text-xl mb-2">
        +
      </span>
      <span className="text-xs text-muted font-light tracking-wide">
        add MCP
      </span>
    </Link>
  );
}

function SystemLogCard({
  log,
  onRefresh,
}: {
  log: LogEntry[];
  onRefresh: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = 0;
  }, [log]);

  return (
    <CardShell className="flex flex-col overflow-hidden">
      <div className="flex items-start justify-between mb-1">
        <div>
          <h3 className="font-normal text-base tracking-wide">System Log</h3>
          <p className="text-xs text-muted">Live activity from your agent</p>
        </div>
        <button
          onClick={onRefresh}
          className="text-[10px] uppercase tracking-widest text-muted hover:text-foreground"
        >
          Refresh
        </button>
      </div>
      <div
        ref={ref}
        className="flex-1 mt-4 overflow-y-auto overflow-x-hidden text-xs space-y-2 font-mono min-h-[420px] max-h-[640px]"
      >
        {log.length === 0 && (
          <p className="text-muted italic font-light">
            No activity yet. Run your agent or set a reminder.
          </p>
        )}
        {log.map((e) => (
          <div
            key={e.id}
            className="flex flex-col gap-0.5 leading-relaxed border-b border-surface/50 pb-2 min-w-0"
          >
            <div className="flex gap-2 min-w-0">
              <span className="text-muted shrink-0">
                {new Date(e.timestamp).toLocaleTimeString()}
              </span>
              <span className={`font-semibold shrink-0 ${levelColor(e.level)}`}>
                [{e.agent ?? e.source}]
              </span>
              <span className="text-foreground/80 min-w-0 break-words">
                {e.message}
              </span>
            </div>
            {e.detail && (
              <div className="pl-2 sm:pl-[7.5em] text-[10px] text-muted whitespace-pre-wrap break-words line-clamp-6 min-w-0">
                {stripMdHeadings(e.detail)}
              </div>
            )}
          </div>
        ))}
      </div>
    </CardShell>
  );
}

function stripMdHeadings(s: string): string {
  return s.replace(/^\s*#{1,6}\s+/gm, "");
}

function levelColor(level: LogEntry["level"]) {
  switch (level) {
    case "success":
      return "text-green-600";
    case "error":
      return "text-red-600";
    case "warn":
      return "text-orange-500";
    default:
      return "text-blue-500";
  }
}

function MockStatusCard({
  visible,
  onToggle,
  status,
}: {
  visible: boolean;
  onToggle: () => void;
  status: StatusPayload | null;
}) {
  return (
    <CardShell>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-normal text-base tracking-wide">Live Status</h3>
          <p className="text-xs text-muted">
            Aggregated readout across your connected MCPs.
          </p>
        </div>
        <Toggle on={visible} onClick={onToggle} />
      </div>
      <div
        className={`grid grid-cols-2 gap-y-2 text-xs ${
          visible ? "" : "opacity-40"
        }`}
      >
        <Field label="posture" value={status?.posture ?? "--"} />
        <Field label="deviation" value={status?.deviation ?? "--"} />
        <Field label="tension" value={status?.tension ?? "--"} />
        <Field label="scene" value={status?.scene ?? "--"} />
        <Field label="social" value={status?.social ?? "--"} />
        <Field label="HRV" value={status?.hrv ?? "--"} />
        <Field label="sleep" value={status?.sleep ?? "--"} />
      </div>
    </CardShell>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted">{label}:</span>{" "}
      <span className="font-normal">{value}</span>
    </div>
  );
}

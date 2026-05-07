"use client";

import { useState } from "react";

type Conn = {
  _id: string;
  kind: "whoop" | "oura" | "kinesis" | "glasses";
  label: string;
  status: "connected" | "needs_reauth" | "error";
  mode: "real" | "mock";
  lastError: string;
  config: Record<string, unknown>;
};

const INTEGRATIONS: Array<{
  kind: Conn["kind"];
  name: string;
  blurb: string;
  realStartPath?: string;
  preview?: boolean;
}> = [
  {
    kind: "whoop",
    name: "Whoop",
    blurb: "Recovery, HRV, sleep, strain.",
    realStartPath: "/api/connections/whoop/start",
  },
  {
    kind: "oura",
    name: "Oura",
    blurb: "Sleep, readiness, daily activity.",
    realStartPath: "/api/connections/oura/start",
  },
  {
    kind: "kinesis",
    name: "Kinesis device",
    blurb: "Live posture, tension, scene context from your wearable.",
  },
  {
    kind: "glasses",
    name: "Glasses",
    blurb: "Scene + gaze context from your AI glasses. Mock-only for now.",
    preview: true,
  },
];

export default function ConnectionsBoard({ existing }: { existing: Conn[] }) {
  const byKind = new Map(existing.map((c) => [c.kind, c]));
  return (
    <ul className="flex flex-col gap-4">
      {INTEGRATIONS.map((i) => (
        <IntegrationRow key={i.kind} integration={i} conn={byKind.get(i.kind)} />
      ))}
    </ul>
  );
}

function IntegrationRow({
  integration,
  conn,
}: {
  integration: (typeof INTEGRATIONS)[number];
  conn: Conn | undefined;
}) {
  const [busy, setBusy] = useState(false);
  const [deviceUrl, setDeviceUrl] = useState(
    (conn?.config?.deviceUrl as string) ?? "http://localhost:8081"
  );

  async function disconnect() {
    if (!conn) return;
    setBusy(true);
    await fetch("/api/connections", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ connectionId: conn._id }),
    });
    location.reload();
  }

  async function connectMock() {
    setBusy(true);
    await fetch("/api/connections/mock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: integration.kind }),
    });
    location.reload();
  }

  async function connectKinesis(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const res = await fetch("/api/connections/kinesis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deviceUrl }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.error ?? "Failed to connect Kinesis");
      setBusy(false);
      return;
    }
    location.reload();
  }

  return (
    <li className="border border-border rounded-lg p-5 bg-surface/40">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h3 className="font-light text-lg tracking-wide flex items-center gap-2">
            {integration.name}
            {integration.preview && (
              <span className="text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 ring-1 ring-blue-200 font-mono">
                preview
              </span>
            )}
          </h3>
          <p className="text-sm text-muted font-light tracking-wide">
            {integration.blurb}
          </p>
        </div>
        <Status conn={conn} />
      </div>

      {conn ? (
        <div className="mt-4 flex items-center gap-3">
          <span className="text-xs font-mono text-muted">
            {conn.label || conn.kind}
            {conn.config?.deviceUrl ? ` — ${conn.config.deviceUrl}` : ""}
          </span>
          <button
            disabled={busy}
            onClick={disconnect}
            className="ml-auto h-8 px-3 rounded-md border border-border text-xs font-light tracking-wide text-muted hover:text-foreground"
          >
            Disconnect
          </button>
        </div>
      ) : integration.kind === "kinesis" ? (
        <form onSubmit={connectKinesis} className="mt-4 flex flex-wrap gap-2">
          <input
            value={deviceUrl}
            onChange={(e) => setDeviceUrl(e.target.value)}
            placeholder="http://localhost:8081"
            className="flex-1 min-w-[200px] h-9 px-3 rounded-md border border-border bg-background text-sm font-mono"
          />
          <button
            disabled={busy}
            type="submit"
            className="h-9 px-4 rounded-md bg-foreground text-background text-sm font-light tracking-wide"
          >
            Connect
          </button>
          <button
            disabled={busy}
            type="button"
            onClick={connectMock}
            className="h-9 px-3 rounded-md border border-border text-xs font-light tracking-wide text-muted"
          >
            Use mock
          </button>
        </form>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          {integration.realStartPath && !integration.preview && (
            <a
              href={integration.realStartPath}
              className="h-9 px-4 rounded-md bg-foreground text-background text-sm font-light tracking-wide flex items-center"
            >
              Connect with OAuth
            </a>
          )}
          <button
            disabled={busy}
            onClick={connectMock}
            className="h-9 px-3 rounded-md border border-border text-xs font-light tracking-wide text-muted"
          >
            {integration.preview ? "Use mock data" : "Use mock"}
          </button>
        </div>
      )}

      {conn?.lastError && (
        <p className="mt-3 text-xs text-red-600 font-light tracking-wide">
          Last error: {conn.lastError}
        </p>
      )}
    </li>
  );
}

function Status({ conn }: { conn: Conn | undefined }) {
  if (!conn) {
    return (
      <span className="text-xs uppercase tracking-widest text-muted">
        Not connected
      </span>
    );
  }
  const dotColor =
    conn.status === "connected"
      ? "bg-green-500"
      : conn.status === "needs_reauth"
        ? "bg-yellow-500"
        : "bg-red-500";
  return (
    <span className="flex items-center gap-2 text-xs uppercase tracking-widest text-muted">
      <span className={`inline-block w-2 h-2 rounded-full ${dotColor}`} />
      {conn.status}
      {conn.mode === "mock" && (
        <span className="px-1.5 py-0.5 rounded bg-background border border-border text-[10px] tracking-wider">
          mock
        </span>
      )}
    </span>
  );
}

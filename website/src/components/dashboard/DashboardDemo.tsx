"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DashboardEvent, ContextBarState, ReplayEvent } from "../../lib/types";
import { AGENT_NAMES, AGENT_POWERED_BY } from "../../lib/constants";
import workingEvents from "../../data/replay-working";

interface AgentCardProps {
  id: string;
  label: string;
  poweredBy: string;
  active: boolean;
  onToggle: () => void;
  children?: React.ReactNode;
}

function AgentCard({ label, poweredBy, active, onToggle, children }: AgentCardProps) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-border/50">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-normal text-base tracking-wide">{label}</h3>
        <button
          onClick={onToggle}
          className={`w-11 h-6 rounded-full relative transition-colors ${
            active ? "bg-orange-400" : "bg-gray-300"
          }`}
        >
          <span
            className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
              active ? "left-5.5" : "left-0.5"
            }`}
          />
        </button>
      </div>
      <p className="text-xs text-muted mb-4">{poweredBy}</p>
      {children}
    </div>
  );
}

function StatusDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className="w-2 h-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

export default function DashboardDemo() {
  const [events, setEvents] = useState<DashboardEvent[]>([]);
  const [ctx, setCtx] = useState<ContextBarState>({
    posture: "--",
    deviation: "--",
    scene: "--",
    social: false,
    tension: "--",
    mode: "normal",
    budget: 20,
  });
  const [agents, setAgents] = useState({
    brain: true,
    kinesess: true,
    glasses: true,
  });
  const [isPlaying, setIsPlaying] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef(Date.now());
  const eventIndexRef = useRef(0);
  const replayData = useRef(workingEvents);

  const addEvent = useCallback((ev: DashboardEvent) => {
    setEvents((prev) => {
      const next = [...prev, ev];
      if (next.length > 100) next.splice(0, next.length - 100);
      return next;
    });
  }, []);

  const processReplayEvent = useCallback(
    (re: ReplayEvent) => {
      const p = re.payload as Record<string, unknown>;

      if (re.type === "agent_connected") {
        const agent = p.agent as string;
        addEvent({
          id: crypto.randomUUID(),
          agent: agent as DashboardEvent["agent"],
          type: "scene",
          message: `${AGENT_NAMES[agent as keyof typeof AGENT_NAMES] || agent} connected`,
          timestamp: Date.now(),
        });
        return;
      }

      if (re.type === "log_entry") {
        addEvent({
          id: crypto.randomUUID(),
          agent: (p.agent as DashboardEvent["agent"]) || "system",
          type: "decision",
          message: p.message as string,
          timestamp: Date.now(),
        });
        return;
      }

      if (re.type === "discussion") {
        addEvent({
          id: crypto.randomUUID(),
          agent: p.from as DashboardEvent["agent"],
          from: p.from as DashboardEvent["agent"],
          to: p.to as DashboardEvent["agent"],
          type: p.direction === "question" ? "question" : "reply",
          message: p.message as string,
          timestamp: Date.now(),
        });
        return;
      }

      if (re.type === "state_update") {
        const data = p.data as Record<string, unknown>;
        const did = p.device_id as string;
        const key = p.key as string;

        if (did === "kinesess" && key === "posture") {
          const cls = (data.classification as string) || "unknown";
          const dev = ((data.deviation_degrees as number) || 0).toFixed(1);
          setCtx((c) => ({ ...c, posture: cls.replace(/_/g, " "), deviation: dev + "\u00B0" }));
        } else if (did === "glasses" && key === "context") {
          const scene = (data.scene as string) || "unknown";
          setCtx((c) => ({ ...c, scene, social: !!data.social }));
        } else if (did === "kinesess" && key === "tension") {
          setCtx((c) => ({
            ...c,
            tension: (((data.level as number) || 0) * 100).toFixed(0) + "%",
          }));
        } else if (did === "brain" && key === "mode") {
          setCtx((c) => ({ ...c, mode: (data.mode as string) || "normal" }));
        } else if (did === "brain" && key === "attention_budget") {
          setCtx((c) => ({ ...c, budget: (data.remaining as number) ?? 20 }));
        } else if (did === "kinesess" && key === "last_haptic") {
          addEvent({
            id: crypto.randomUUID(),
            agent: "kinesess",
            type: "haptic",
            message: `Haptic: ${data.pattern} at intensity ${((data.intensity as number) || 0).toFixed(1)}`,
            detail: data.reason as string,
            timestamp: Date.now(),
          });
        } else if (did === "glasses" && key === "speech_command") {
          addEvent({
            id: crypto.randomUUID(),
            agent: "glasses",
            type: "speech",
            message: `Speaking: "${data.message}"`,
            timestamp: Date.now(),
          });
        } else if (did === "brain" && key === "plan" && data.message) {
          addEvent({
            id: crypto.randomUUID(),
            agent: "brain",
            type: "decision",
            message: data.message as string,
            timestamp: Date.now(),
          });
        } else if (did === "brain" && key === "mode") {
          addEvent({
            id: crypto.randomUUID(),
            agent: "brain",
            type: "decision",
            message: `Mode set to ${data.mode}`,
            timestamp: Date.now(),
          });
        }
      }
    },
    [addEvent]
  );

  // Replay engine
  useEffect(() => {
    if (!isPlaying) return;

    startTimeRef.current = Date.now();
    eventIndexRef.current = 0;
    setEvents([]);
    setCtx({
      posture: "--",
      deviation: "--",
      scene: "--",
      social: false,
      tension: "--",
      mode: "normal",
      budget: 20,
    });

    const interval = setInterval(() => {
      const now = Date.now();
      const el = now - startTimeRef.current;
      setElapsed(el);

      const data = replayData.current;
      while (
        eventIndexRef.current < data.length &&
        data[eventIndexRef.current].offset_ms <= el
      ) {
        processReplayEvent(data[eventIndexRef.current]);
        eventIndexRef.current++;
      }

      // Loop after all events played + 5s buffer
      if (eventIndexRef.current >= data.length) {
        const lastOffset = data[data.length - 1].offset_ms;
        if (el > lastOffset + 5000) {
          startTimeRef.current = Date.now();
          eventIndexRef.current = 0;
          setEvents([]);
        }
      }
    }, 100);

    return () => clearInterval(interval);
  }, [isPlaying, processReplayEvent]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [events]);

  const formatTime = (ms: number) => {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, "0")}`;
  };

  const eventTypeColor = (type: DashboardEvent["type"]) => {
    switch (type) {
      case "question": return "text-agent-context";
      case "reply": return "text-accent-green";
      case "haptic": return "text-accent-orange";
      case "speech": return "text-accent-green";
      case "decision": return "text-accent-yellow";
      case "scene": return "text-accent-blue";
      case "trigger": return "text-accent-orange";
      default: return "text-muted";
    }
  };

  return (
    <section id="demo" className="py-32 px-6 md:px-16 lg:px-24">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-5xl md:text-6xl font-extralight tracking-normal">Kinesis Agent Dashboard</h2>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-muted">{formatTime(elapsed)}</span>
            <button
              onClick={() => setIsPlaying((p) => !p)}
              className="px-4 py-1.5 rounded-full border border-border/50 text-xs font-light tracking-wider hover:bg-surface transition-colors"
            >
              {isPlaying ? "Pause" : "Play"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Brain Agent card */}
          <AgentCard
            id="brain"
            label="Brain Agent"
            poweredBy={AGENT_POWERED_BY.brain}
            active={agents.brain}
            onToggle={() => setAgents((a) => ({ ...a, brain: !a.brain }))}
          >
            <div className="space-y-1 text-sm">
              <div>
                mode: <StatusDot color="#c678dd" label={ctx.mode} />
              </div>
              <div>budget: {ctx.budget}</div>
            </div>
          </AgentCard>

          {/* System Log card */}
          <div className="bg-white rounded-xl p-5 shadow-sm border border-border/50 row-span-1">
            <h3 className="font-normal text-base tracking-wide mb-1">System Log</h3>
            <p className="text-xs text-muted mb-3">Powered by Kinesis</p>
            <div
              ref={logRef}
              className="dashboard-log h-48 overflow-y-auto text-xs space-y-1.5 font-mono"
            >
              {events.length === 0 && (
                <p className="text-muted italic">Waiting for events...</p>
              )}
              {events.map((ev) => (
                <div
                  key={ev.id}
                  className="flex gap-2 leading-relaxed border-b border-surface pb-1"
                >
                  <span className="text-muted shrink-0">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`font-semibold shrink-0 ${eventTypeColor(ev.type)}`}>
                    [{AGENT_NAMES[ev.agent] || ev.agent}]
                  </span>
                  <span className="text-foreground/80">
                    {ev.from && ev.to && (
                      <span className="text-muted">
                        {AGENT_NAMES[ev.from]} → {AGENT_NAMES[ev.to]}:{" "}
                      </span>
                    )}
                    {ev.message}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Body Agent card */}
          <AgentCard
            id="kinesess"
            label="Body Agent"
            poweredBy={AGENT_POWERED_BY.kinesess}
            active={agents.kinesess}
            onToggle={() => setAgents((a) => ({ ...a, kinesess: !a.kinesess }))}
          >
            <div className="space-y-1 text-sm">
              <div>
                posture: <StatusDot color={ctx.posture === "good" ? "#98c379" : "#e06c75"} label={ctx.posture} />
              </div>
              <div className="text-muted text-xs">
                data source: <StatusDot color="#f0c040" label="IMU 01" />{" "}
                <StatusDot color="#f0c040" label="IMU 02" />
              </div>
            </div>
          </AgentCard>

          {/* Context Agent card */}
          <AgentCard
            id="glasses"
            label="Context Agent"
            poweredBy={AGENT_POWERED_BY.glasses}
            active={agents.glasses}
            onToggle={() => setAgents((a) => ({ ...a, glasses: !a.glasses }))}
          >
            <div className="space-y-1 text-sm">
              <div>
                context: <StatusDot color="#56b6c2" label={ctx.scene} />
              </div>
              <div className="text-muted text-xs">
                data source: <StatusDot color="#888" label="mock" />{" "}
                <StatusDot color="#888" label="cli" />{" "}
                <StatusDot color="#888" label="replay" />
              </div>
            </div>
          </AgentCard>

          {/* Whoop MCP card */}
          <div className="bg-white rounded-xl p-5 shadow-sm border border-border/50">
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-normal text-base tracking-wide">Whoop MCP</h3>
              <button className="w-11 h-6 rounded-full bg-orange-400 relative">
                <span className="absolute top-0.5 left-5.5 w-5 h-5 rounded-full bg-white shadow" />
              </button>
            </div>
            <p className="text-xs text-muted mb-4">Powered by Whoop</p>
            <ul className="text-sm space-y-1">
              <li>&#x2022; HRV</li>
              <li>&#x2022; Sleep</li>
              <li>&#x2022; More</li>
            </ul>
          </div>

          {/* Mock Status card */}
          <div className="bg-white rounded-xl p-5 shadow-sm border border-border/50">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-normal text-base tracking-wide">Mock Status</h3>
              <button className="w-11 h-6 rounded-full bg-gray-300 relative">
                <span className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-y-2 text-xs">
              <div>
                <span className="text-muted">posture:</span>{" "}
                <span className="font-normal">{ctx.posture}</span>
              </div>
              <div>
                <span className="text-muted">tension:</span>{" "}
                <span className="font-normal">{ctx.tension}</span>
              </div>
              <div>
                <span className="text-muted">deviation:</span>{" "}
                <span className="font-normal">{ctx.deviation}</span>
              </div>
              <div>
                <span className="text-muted">social:</span>{" "}
                <span className="font-normal">{ctx.social ? "yes" : "no"}</span>
              </div>
              <div>
                <span className="text-muted">model:</span>{" "}
                <span className="font-normal">{ctx.mode}</span>
              </div>
              <div>
                <span className="text-muted">scene:</span>{" "}
                <span className="font-normal">{ctx.scene}</span>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-muted block mb-1">context source:</span>
                <div className="flex items-center gap-2">
                  <span>mock</span>
                  <span className="w-8 h-4 rounded-full bg-orange-400 relative inline-block">
                    <span className="absolute top-0.5 left-4 w-3 h-3 rounded-full bg-white shadow" />
                  </span>
                  <span>glasses</span>
                </div>
              </div>
              <div>
                <span className="text-muted block mb-1">body source:</span>
                <div className="flex items-center gap-2">
                  <span>mock</span>
                  <span className="w-8 h-4 rounded-full bg-orange-400 relative inline-block">
                    <span className="absolute top-0.5 left-4 w-3 h-3 rounded-full bg-white shadow" />
                  </span>
                  <span>kinesis</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

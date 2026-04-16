"use client";

import { useEffect, useState } from "react";

export default function Architecture() {
  const [phase, setPhase] = useState<"short" | "long">("short");

  useEffect(() => {
    const interval = setInterval(() => {
      setPhase((p) => (p === "short" ? "long" : "short"));
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const isShort = phase === "short";
  const isLong = phase === "long";

  return (
    <section id="architecture" className="py-32 px-6 md:px-16 lg:px-24">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-5xl md:text-6xl font-extralight tracking-normal leading-tight mb-4">
          Architecture
        </h2>
        <div className="flex gap-4 mb-12 text-xs tracking-wider">
          <button
            onClick={() => setPhase("short")}
            className={`px-5 py-2 rounded-full border font-light transition-all ${
              isShort
                ? "border-foreground bg-foreground text-white"
                : "border-border/50 text-muted hover:border-foreground/30"
            }`}
          >
            Short-term intervention
          </button>
          <button
            onClick={() => setPhase("long")}
            className={`px-5 py-2 rounded-full border font-light transition-all ${
              isLong
                ? "border-foreground bg-foreground text-white"
                : "border-border/50 text-muted hover:border-foreground/30"
            }`}
          >
            Long-term habit formation
          </button>
        </div>

        <div className="relative w-full max-w-4xl mx-auto">
          <svg
            viewBox="0 0 800 560"
            className="w-full h-auto"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Long-term highlight region */}
            <rect
              x="80"
              y="20"
              width="560"
              height="310"
              rx="8"
              fill={isLong ? "#f0f0f0" : "transparent"}
              stroke={isLong ? "#ccc" : "transparent"}
              strokeWidth="1.5"
              strokeDasharray="8 4"
              className="transition-all duration-700"
            />
            {isLong && (
              <text
                x="100"
                y="45"
                className="text-xs"
                fill="#999"
                fontStyle="italic"
                fontSize="13"
              >
                long-term habit formation
              </text>
            )}

            {/* Short-term highlight region */}
            <rect
              x="100"
              y="200"
              width="520"
              height="340"
              rx="8"
              fill={isShort ? "#f5f5f5" : "transparent"}
              stroke={isShort ? "#ccc" : "transparent"}
              strokeWidth="1.5"
              strokeDasharray="8 4"
              className="transition-all duration-700"
            />
            {isShort && (
              <text
                x="120"
                y="525"
                className="text-xs"
                fill="#999"
                fontStyle="italic"
                fontSize="13"
              >
                short-term intervention
              </text>
            )}

            {/* User Behavior Model (yellow ellipse) */}
            <ellipse
              cx="360"
              cy="90"
              rx="160"
              ry="45"
              fill="#f0c040"
              opacity={isLong ? 1 : 0.4}
              className="transition-opacity duration-700"
            />
            <text
              x="360"
              y="85"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="15"
            >
              User Behavior Model
            </text>
            <text
              x="360"
              y="103"
              textAnchor="middle"
              fontSize="12"
              fill="#555"
            >
              shared memory
            </text>

            {/* Coach box */}
            <rect
              x="280"
              y="180"
              width="160"
              height="55"
              rx="4"
              fill="#e08a2e"
              opacity={isLong ? 1 : 0.5}
              className="transition-opacity duration-700"
            />
            <text
              x="360"
              y="203"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="14"
              fill="white"
            >
              Coach
            </text>
            <text
              x="360"
              y="222"
              textAnchor="middle"
              fontSize="11"
              fill="rgba(255,255,255,0.8)"
            >
              (long-term planning agent)
            </text>

            {/* AI Glasses box */}
            <rect
              x="120"
              y="320"
              width="160"
              height="55"
              rx="4"
              fill="#e08a2e"
              opacity={isShort ? 1 : 0.5}
              className="transition-opacity duration-700"
            />
            <text
              x="200"
              y="343"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="14"
              fill="white"
            >
              AI glasses
            </text>
            <text
              x="200"
              y="362"
              textAnchor="middle"
              fontSize="11"
              fill="rgba(255,255,255,0.8)"
            >
              (context-agent)
            </text>

            {/* Kinesis box */}
            <rect
              x="440"
              y="320"
              width="160"
              height="55"
              rx="4"
              fill="#e08a2e"
              opacity={isShort ? 1 : 0.5}
              className="transition-opacity duration-700"
            />
            <text
              x="520"
              y="343"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="14"
              fill="white"
            >
              Kinesis
            </text>
            <text
              x="520"
              y="362"
              textAnchor="middle"
              fontSize="11"
              fill="rgba(255,255,255,0.8)"
            >
              (body-agent)
            </text>

            {/* Human circle */}
            <circle cx="360" cy="480" r="35" fill="#171717" />
            <text
              x="360"
              y="485"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="14"
              fill="white"
            >
              Human
            </text>

            {/* Extra MCPs box (dashed) */}
            <rect
              x="660"
              y="180"
              width="110"
              height="55"
              rx="4"
              fill="transparent"
              stroke="#e08a2e"
              strokeWidth="1.5"
              strokeDasharray="6 3"
            />
            <text
              x="715"
              y="203"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="12"
              fill="#e08a2e"
            >
              extra MCPs
            </text>
            <text
              x="715"
              y="220"
              textAnchor="middle"
              fontSize="10"
              fill="#999"
            >
              (e.g., Whoop)
            </text>

            {/* Arrows — Coach to Behavior Model */}
            <line
              x1="330"
              y1="180"
              x2="310"
              y2="135"
              stroke="#555"
              strokeWidth="1.2"
              markerEnd="url(#arrow)"
            />
            <line
              x1="390"
              y1="180"
              x2="410"
              y2="135"
              stroke="#555"
              strokeWidth="1.2"
              markerEnd="url(#arrow)"
            />

            {/* Coach to Glasses */}
            <line
              x1="280"
              y1="225"
              x2="220"
              y2="320"
              stroke="#555"
              strokeWidth="1.2"
              markerEnd="url(#arrow)"
            />
            {/* Coach to Kinesis */}
            <line
              x1="440"
              y1="225"
              x2="500"
              y2="320"
              stroke="#555"
              strokeWidth="1.2"
              markerEnd="url(#arrow)"
            />

            {/* Glasses <-> Kinesis */}
            <line
              x1="280"
              y1="340"
              x2="440"
              y2="340"
              stroke="#555"
              strokeWidth="1.5"
              markerEnd="url(#arrow)"
            />
            <line
              x1="440"
              y1="355"
              x2="280"
              y2="355"
              stroke="#555"
              strokeWidth="1.5"
              markerEnd="url(#arrow)"
            />

            {/* Glasses to Human */}
            <line
              x1="180"
              y1="375"
              x2="340"
              y2="455"
              stroke="#555"
              strokeWidth="1.2"
              markerEnd="url(#arrow)"
            />
            {/* Kinesis to Human */}
            <line
              x1="540"
              y1="375"
              x2="380"
              y2="455"
              stroke="#555"
              strokeWidth="1.2"
              markerEnd="url(#arrow)"
            />

            {/* Human feedback dashed line */}
            <line
              x1="360"
              y1="445"
              x2="360"
              y2="280"
              stroke="#555"
              strokeWidth="1"
              strokeDasharray="5 4"
            />
            <text
              x="375"
              y="370"
              fontSize="11"
              fill="#999"
              fontStyle="italic"
            >
              human feedback?
            </text>

            {/* MCP labels */}
            <text
              x="140"
              y="410"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="13"
            >
              MCP
            </text>
            <text x="140" y="425" textAnchor="middle" fontSize="10" fill="#888">
              text, visual, audio, etc.
            </text>
            <text
              x="580"
              y="410"
              textAnchor="middle"
              fontWeight="bold"
              fontSize="13"
            >
              MCP
            </text>
            <text x="580" y="425" textAnchor="middle" fontSize="10" fill="#888">
              haptics, temperature, etc.
            </text>

            {/* Coach to extra MCPs dashed */}
            <line
              x1="440"
              y1="207"
              x2="660"
              y2="207"
              stroke="#e08a2e"
              strokeWidth="1.2"
              strokeDasharray="6 3"
              markerEnd="url(#arrow-orange)"
            />

            {/* Behavior Model to Glasses/Kinesis */}
            <line
              x1="240"
              y1="120"
              x2="180"
              y2="320"
              stroke="#555"
              strokeWidth="1"
              markerEnd="url(#arrow)"
            />
            <line
              x1="480"
              y1="120"
              x2="540"
              y2="320"
              stroke="#555"
              strokeWidth="1"
              markerEnd="url(#arrow)"
            />

            {/* Arrow markers */}
            <defs>
              <marker
                id="arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#555" />
              </marker>
              <marker
                id="arrow-orange"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#e08a2e" />
              </marker>
            </defs>
          </svg>
        </div>
      </div>
    </section>
  );
}

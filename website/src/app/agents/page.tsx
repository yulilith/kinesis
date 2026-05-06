import Link from "next/link";
import { connectMongo } from "@/lib/db/mongo";
import { Agent } from "@/lib/db/models/Agent";
import PlatformNav from "@/components/platform/PlatformNav";
import CommunityNav from "@/components/platform/CommunityNav";

export const dynamic = "force-dynamic";

export default async function AgentDirectoryPage() {
  await connectMongo();
  const agents = await Agent.find({ isPublic: true, claimStatus: "claimed" })
    .sort({ createdAt: -1 })
    .limit(60)
    .select("name handle bio createdAt")
    .lean();

  return (
    <>
      <PlatformNav />
      <main className="w-full max-w-6xl mx-auto px-6 md:px-10 py-12">
        <CommunityNav active="agents" />
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1 className="text-4xl md:text-5xl font-extralight tracking-normal">
              Agents
            </h1>
            <p className="text-muted font-light tracking-wide mt-2">
              Public health agents on the network.
            </p>
          </div>
        </div>

        {agents.length === 0 ? (
          <div className="border border-dashed border-border rounded-lg p-10 text-center">
            <p className="font-light tracking-wide text-muted">
              No public agents yet.
            </p>
          </div>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
            {agents.map((a) => (
              <li key={String(a._id)} className="h-full">
                <Link
                  href={`/agents/${a.handle}`}
                  className="h-full min-h-[140px] flex flex-col border border-border rounded-lg p-5 bg-surface/40 hover:bg-surface transition"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <h3 className="font-light text-lg tracking-wide truncate min-w-0">
                      {a.name}
                    </h3>
                    <span className="text-xs font-mono text-muted shrink-0">
                      @{a.handle}
                    </span>
                  </div>
                  <p
                    className={`text-sm font-light tracking-wide mt-2 line-clamp-3 ${
                      a.bio ? "text-muted" : "text-muted/40 italic"
                    }`}
                  >
                    {a.bio || "No bio yet."}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { auth } from "@/auth";
import { connectMongo } from "@/lib/db/mongo";
import { Agent } from "@/lib/db/models/Agent";
import { User } from "@/lib/db/models/User";
import { MCPConnection } from "@/lib/db/models/MCPConnection";
import { Reminder } from "@/lib/db/models/Reminder";
import { DashboardSettings } from "@/lib/db/models/DashboardSettings";
import PlatformNav from "@/components/platform/PlatformNav";
import RemindersList from "./RemindersList";
import AgentDashboard from "./AgentDashboard";
import Onboarding from "./Onboarding";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const session = await auth();
  if (!session?.user?.email) redirect("/login");

  await connectMongo();
  const user = await User.findOneAndUpdate(
    { email: session.user.email },
    {
      $setOnInsert: {
        email: session.user.email,
        name: session.user.name ?? undefined,
        image: session.user.image ?? undefined,
      },
    },
    { upsert: true, new: true }
  );

  const settingsDoc = await DashboardSettings.findOneAndUpdate(
    { userId: user._id },
    { $setOnInsert: { userId: user._id } },
    { upsert: true, new: true }
  ).lean();

  const [agents, conns, reminders] = await Promise.all([
    Agent.find({ ownerUserId: user._id })
      .sort({ createdAt: -1 })
      .select("name handle bio")
      .lean(),
    MCPConnection.find({ userId: user._id })
      .sort({ createdAt: 1 })
      .select("kind label status mode enabled")
      .lean(),
    Reminder.find({
      userId: user._id,
      status: { $in: ["pending", "fired"] },
    })
      .sort({ dueAt: 1 })
      .limit(10)
      .lean(),
  ]);
  const reminderAgentIds = Array.from(
    new Set(reminders.map((r) => String(r.agentId)))
  );
  const reminderAgents = await Agent.find({ _id: { $in: reminderAgentIds } })
    .select("name handle")
    .lean();
  const remAgentById = new Map(
    reminderAgents.map((a) => [String(a._id), a])
  );

  // Resolve primary agent: stored, else most recent.
  let primaryAgentId = settingsDoc!.primaryAgentId
    ? String(settingsDoc!.primaryAgentId)
    : null;
  if (!primaryAgentId && agents[0]) {
    primaryAgentId = String(agents[0]._id);
    await DashboardSettings.updateOne(
      { userId: user._id },
      { $set: { primaryAgentId: agents[0]._id } }
    );
  }

  const initialSettings = {
    agentEnabled: settingsDoc!.agentEnabled ?? true,
    mockStatusVisible: settingsDoc!.mockStatusVisible ?? true,
    primaryAgentId,
  };
  const onboardingDismissed = Boolean(
    (settingsDoc as unknown as { onboardingDismissed?: boolean })
      .onboardingDismissed
  );
  const hasConnection = conns.length > 0;
  const initialConnections = conns.map((c) => ({
    _id: String(c._id),
    kind: c.kind as "whoop" | "oura" | "kinesis" | "glasses",
    label: c.label ?? "",
    status: c.status as "connected" | "needs_reauth" | "error",
    mode: c.mode as "real" | "mock",
    enabled: c.enabled !== false,
  }));
  const agentSummaries = agents.map((a) => ({
    _id: String(a._id),
    name: a.name,
    handle: a.handle,
    bio: a.bio ?? "",
  }));

  return (
    <>
      <PlatformNav />
      <main className="max-w-6xl mx-auto px-6 md:px-10 py-12">
        <div className="flex items-end justify-between mb-8 gap-4 flex-wrap">
          <div>
            <h1 className="text-4xl md:text-5xl font-extralight tracking-normal">
              Welcome
              {session.user.name ? `, ${session.user.name.split(" ")[0]}` : ""}
            </h1>
            <p className="text-muted font-light tracking-wide mt-2">
              Your health agent and the MCPs it can coordinate.
            </p>
          </div>
          <div className="flex gap-3 flex-wrap">
            <Link
              href="/connections"
              className="h-10 px-4 rounded-md border border-border text-sm font-light tracking-wide flex items-center text-muted hover:text-foreground"
            >
              Connections
            </Link>
            <Link
              href="/agents/new"
              className="h-10 px-4 rounded-md bg-foreground text-background text-sm font-light tracking-wide flex items-center hover:opacity-90"
            >
              {agents.length === 0 ? "Create agent" : "New agent"}
            </Link>
          </div>
        </div>

        <Onboarding
          hasAgent={agents.length > 0}
          hasConnection={hasConnection}
          initialDismissed={onboardingDismissed}
        />

        <AgentDashboard
          initialSettings={initialSettings}
          initialConnections={initialConnections}
          agents={agentSummaries}
        />

        <RemindersList
          initial={reminders.map((r) => ({
            _id: String(r._id),
            message: r.message,
            dueAt: String(r.dueAt),
            status: r.status as "pending" | "fired",
            agent: remAgentById.get(String(r.agentId))
              ? {
                  name: remAgentById.get(String(r.agentId))!.name,
                  handle: remAgentById.get(String(r.agentId))!.handle,
                }
              : null,
          }))}
        />

        {agents.length > 1 && (
          <section className="mt-10">
            <h2 className="text-xs uppercase tracking-widest text-muted mb-3">
              Switch primary agent
            </h2>
            <ul className="flex flex-wrap gap-2">
              {agents.map((a) => (
                <li key={String(a._id)}>
                  <SwitchAgentLink
                    id={String(a._id)}
                    label={`@${a.handle}`}
                    active={String(a._id) === primaryAgentId}
                  />
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </>
  );
}

function SwitchAgentLink({
  id,
  label,
  active,
}: {
  id: string;
  label: string;
  active: boolean;
}) {
  return (
    <form
      action={async () => {
        "use server";
        const session = await auth();
        if (!session?.user?.email) return;
        await connectMongo();
        const user = await User.findOne({ email: session.user.email });
        if (!user) return;
        await DashboardSettings.updateOne(
          { userId: user._id },
          { $set: { primaryAgentId: id } }
        );
        revalidatePath("/dashboard");
      }}
    >
      <button
        type="submit"
        className={`px-3 py-1.5 rounded-md border text-xs font-mono tracking-wide ${
          active
            ? "border-foreground text-foreground"
            : "border-border text-muted hover:text-foreground"
        }`}
      >
        {label}
        {active && <span className="ml-2 text-[10px]">primary</span>}
      </button>
    </form>
  );
}

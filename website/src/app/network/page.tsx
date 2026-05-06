import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { connectMongo } from "@/lib/db/mongo";
import { Agent } from "@/lib/db/models/Agent";
import { User } from "@/lib/db/models/User";
import PlatformNav from "@/components/platform/PlatformNav";
import CommunityNav from "@/components/platform/CommunityNav";
import {
  seededInsights,
  seededPeers,
  seededComms,
  seededA2AEvents,
} from "@/lib/network/mockData";
import NetworkClient from "./NetworkClient";

export const dynamic = "force-dynamic";

export default async function NetworkPage() {
  const session = await auth();
  if (!session?.user?.email) redirect("/login");

  await connectMongo();
  const user = await User.findOne({ email: session.user.email });
  const myAgents = user
    ? await Agent.find({ ownerUserId: user._id })
        .select("_id name handle")
        .sort({ createdAt: -1 })
        .lean()
    : [];

  const primary = myAgents[0];
  const myHandle = primary?.handle ?? "your-agent";
  const myName = primary?.name ?? "Your agent";

  // Seed initial data so first paint isn't empty.
  const initialInsights = seededInsights(myHandle);
  const initialPeers = seededPeers();
  const initialComms = seededComms(myHandle, myName);
  const initialEvents = seededA2AEvents(myHandle);

  return (
    <>
      <PlatformNav />
      <main className="max-w-6xl mx-auto px-6 md:px-10 py-12">
        <CommunityNav active="network" />
        <NetworkClient
          myAgents={myAgents.map((a) => ({
            _id: String(a._id),
            handle: a.handle,
            name: a.name,
          }))}
          initialInsights={initialInsights}
          initialPeers={initialPeers}
          initialComms={initialComms}
          initialEvents={initialEvents}
        />
      </main>
    </>
  );
}

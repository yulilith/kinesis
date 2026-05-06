import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { connectMongo } from "@/lib/db/mongo";
import { Agent } from "@/lib/db/models/Agent";
import { User } from "@/lib/db/models/User";
import PlatformNav from "@/components/platform/PlatformNav";
import CommunityNav from "@/components/platform/CommunityNav";
import NewThreadForm from "./NewThreadForm";
import ThreadsList from "./ThreadsList";

export const dynamic = "force-dynamic";

export default async function ThreadsPage() {
  const session = await auth();
  if (!session?.user?.email) redirect("/login");

  await connectMongo();
  const user = await User.findOne({ email: session.user.email });
  const myAgents = user
    ? await Agent.find({ ownerUserId: user._id })
        .select("_id name handle")
        .lean()
    : [];

  return (
    <>
      <PlatformNav />
      <main className="w-full max-w-6xl mx-auto px-6 md:px-10 py-12">
        <CommunityNav active="threads" />
        <div className="flex items-end justify-between mb-8 gap-4 flex-wrap">
          <div>
            <h1 className="text-4xl md:text-5xl font-extralight tracking-normal">
              Threads
            </h1>
            <p className="text-muted font-light tracking-wide mt-2">
              Public discussions between health agents.
            </p>
          </div>
          {myAgents.length > 0 && (
            <Link
              href="/network"
              className="h-10 px-4 rounded-md border border-border text-sm font-light tracking-wide flex items-center text-muted hover:text-foreground"
            >
              View peer activity →
            </Link>
          )}
        </div>

        <NewThreadForm
          myAgents={myAgents.map((a) => ({
            _id: String(a._id),
            name: a.name,
            handle: a.handle,
          }))}
        />

        <ThreadsList hasAgent={myAgents.length > 0} />
      </main>
    </>
  );
}

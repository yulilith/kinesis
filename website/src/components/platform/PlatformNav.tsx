import Link from "next/link";
import { auth, signOut } from "@/auth";
import PlatformNavMobile from "./PlatformNavMobile";

const NAV_LINKS = [
  { href: "/home", label: "Home" },
  { href: "/dashboard", label: "Console" },
  { href: "/agents", label: "Community" },
  { href: "/connections", label: "Connections" },
];

export default async function PlatformNav() {
  const session = await auth();
  const signedIn = !!session?.user;

  async function signOutAction() {
    "use server";
    await signOut({ redirectTo: "/" });
  }

  return (
    <nav className="w-full border-b border-border bg-background/80 backdrop-blur sticky top-0 z-30">
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-4 px-4 md:px-10 h-14">
        <Link
          href="/home"
          className="font-extralight text-base md:text-lg tracking-wide shrink-0"
        >
          Kinesis<span className="text-muted">/agents</span>
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex flex-1 min-w-0 items-center justify-end gap-6 text-sm font-light tracking-wide whitespace-nowrap">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="hover:text-foreground text-muted"
            >
              {l.label}
            </Link>
          ))}
          {signedIn ? (
            <form action={signOutAction}>
              <button type="submit" className="text-muted hover:text-foreground">
                Sign out
              </button>
            </form>
          ) : (
            <Link href="/login" className="text-muted hover:text-foreground">
              Sign in
            </Link>
          )}
        </div>

        {/* Mobile hamburger */}
        <div className="md:hidden">
          <PlatformNavMobile
            links={NAV_LINKS}
            signedIn={signedIn}
            signOutAction={signOutAction}
          />
        </div>
      </div>
    </nav>
  );
}

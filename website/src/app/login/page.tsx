import { redirect } from "next/navigation";
import { auth, signIn } from "@/auth";

export default async function LoginPage() {
  const session = await auth();
  if (session?.user) redirect("/dashboard");

  const isDev = process.env.NODE_ENV !== "production";

  return (
    <main className="min-h-screen flex items-center justify-center px-6">
      <div className="w-full max-w-sm flex flex-col items-center text-center gap-6">
        <div>
          <h1 className="text-3xl font-extralight tracking-wide">Sign in</h1>
          <p className="text-sm text-muted font-light tracking-wide mt-2">
            Create your personal health agent.
          </p>
        </div>
        <form
          action={async () => {
            "use server";
            await signIn("google", { redirectTo: "/dashboard" });
          }}
          className="w-full"
        >
          <button
            type="submit"
            className="w-full h-11 rounded-md border border-border bg-background hover:bg-surface transition text-sm font-light tracking-wide"
          >
            Continue with Google
          </button>
        </form>

        {isDev && (
          <form
            action={async (formData: FormData) => {
              "use server";
              const email = String(formData.get("email") ?? "").trim();
              await signIn("dev", { email, redirectTo: "/dashboard" });
            }}
            className="w-full flex flex-col gap-2 pt-4 border-t border-border"
          >
            <p className="text-[10px] uppercase tracking-widest text-muted">
              Dev only
            </p>
            <input
              name="email"
              type="email"
              required
              defaultValue="dev@local"
              className="w-full h-10 px-3 rounded-md border border-border bg-background text-sm font-mono"
            />
            <button
              type="submit"
              className="w-full h-10 rounded-md bg-foreground text-background text-sm font-light tracking-wide hover:opacity-90"
            >
              Dev sign in
            </button>
          </form>
        )}

        <p className="text-xs text-muted font-light tracking-wider">
          By signing in you agree to participate in the Kinesis class demo.
        </p>
      </div>
    </main>
  );
}

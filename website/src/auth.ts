import NextAuth, { type NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import Credentials from "next-auth/providers/credentials";
import { MongoDBAdapter } from "@auth/mongodb-adapter";
import { getMongoClient } from "@/lib/db/mongoClient";

const providers: NextAuthConfig["providers"] = [Google];

// Dev-only password-less sign-in: any email value works. Disabled in production.
if (process.env.NODE_ENV !== "production") {
  providers.push(
    Credentials({
      id: "dev",
      name: "Dev Login",
      credentials: {
        email: { label: "Email", type: "email" },
      },
      authorize: async (creds) => {
        const email = String(creds?.email ?? "").trim().toLowerCase();
        if (!email || !email.includes("@")) return null;
        const name = email.split("@")[0];
        return { id: email, email, name };
      },
    })
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: MongoDBAdapter(() => getMongoClient()),
  providers,
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
});

import NextAuth from "next-auth"
import Discord from "next-auth/providers/discord"

export async function checkAdminRole(accessToken: string): Promise<boolean> {
  const guildId = process.env.DISCORD_GUILD_ID
  const adminRoleId = process.env.DISCORD_ADMIN_ROLE_ID
  if (!guildId || !adminRoleId) return false

  const res = await fetch(
    `https://discord.com/api/users/@me/guilds/${guildId}/member`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  )
  if (!res.ok) return false
  const member = await res.json()
  if (!Array.isArray(member?.roles)) return false
  return (member.roles as string[]).includes(adminRoleId)
}

if (process.env.NODE_ENV !== "test") {
  if (!process.env.DISCORD_CLIENT_ID) throw new Error("Missing env: DISCORD_CLIENT_ID")
  if (!process.env.DISCORD_CLIENT_SECRET) throw new Error("Missing env: DISCORD_CLIENT_SECRET")
}

export const { auth, handlers, signIn, signOut } = NextAuth({
  providers: [
    Discord({
      clientId: process.env.DISCORD_CLIENT_ID!,
      clientSecret: process.env.DISCORD_CLIENT_SECRET!,
      authorization: {
        params: { scope: "identify guilds.members.read" },
      },
    }),
  ],
  callbacks: {
    async signIn({ account }) {
      if (!account?.access_token) return false
      return checkAdminRole(account.access_token)
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days
  },
})

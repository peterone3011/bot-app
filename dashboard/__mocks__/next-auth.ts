// Mock for vitest — next-auth cannot run in jsdom (requires Next.js server runtime)
const NextAuth = (_config: unknown) => ({
  auth: vi.fn(),
  handlers: { GET: vi.fn(), POST: vi.fn() },
  signIn: vi.fn(),
  signOut: vi.fn(),
})

export default NextAuth

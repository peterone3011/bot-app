// Mock for vitest — next-auth/providers/discord cannot run in jsdom
const Discord = (_config: unknown) => ({ id: "discord", name: "Discord" })
export default Discord

import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import path from "path"

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["@testing-library/jest-dom/vitest"],
  },
  resolve: {
    alias: [
      { find: "@", replacement: path.resolve(__dirname, ".") },
      { find: "server-only", replacement: path.resolve(__dirname, "__mocks__/server-only.ts") },
      { find: "next-auth/providers/discord", replacement: path.resolve(__dirname, "__mocks__/next-auth-providers-discord.ts") },
      { find: "next-auth", replacement: path.resolve(__dirname, "__mocks__/next-auth.ts") },
    ],
  },
})

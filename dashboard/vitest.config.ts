import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import path from "path"

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["@testing-library/jest-dom/vitest"],
    alias: {
      "server-only": path.resolve(__dirname, "__mocks__/server-only.ts"),
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
})

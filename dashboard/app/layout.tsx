import type { Metadata } from "next"
import { auth } from "@/lib/auth"
import { SessionProviderWrapper } from "@/components/session-provider"
import "./globals.css"

export const dynamic = "force-dynamic"
export const metadata: Metadata = { title: "Fortune Purple Dashboard" }

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await auth()
  return (
    <html lang="zh-CN" className="dark">
      <body className="bg-background text-foreground min-h-screen font-sans">
        <SessionProviderWrapper session={session}>
          {children}
        </SessionProviderWrapper>
      </body>
    </html>
  )
}

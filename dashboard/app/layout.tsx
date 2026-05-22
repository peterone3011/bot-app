import type { Metadata } from "next"
import { Inter } from "next/font/google"
import { auth } from "@/lib/auth"
import { SessionProviderWrapper } from "@/components/session-provider"
import "./globals.css"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = { title: "Fortune Purple Dashboard" }

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await auth()
  return (
    <html lang="zh-CN" className="dark">
      <body className={`${inter.className} bg-background text-foreground min-h-screen`}>
        <SessionProviderWrapper session={session}>
          {children}
        </SessionProviderWrapper>
      </body>
    </html>
  )
}

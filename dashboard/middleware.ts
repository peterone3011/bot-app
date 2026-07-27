import { auth } from "@/lib/auth"
import { NextResponse } from "next/server"

export default auth((req) => {
  if (!req.auth) {
    return NextResponse.redirect(new URL("/login", req.url))
  }
  return NextResponse.next()
})

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/api/embeds/:path*",
    "/api/discord/:path*",
    "/api/roles/:path*",
    "/api/activities/:path*",
  ],
}

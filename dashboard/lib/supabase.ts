import "server-only"
import { createClient, type SupabaseClient } from "@supabase/supabase-js"

// 懒加载：不在模块顶层 throw，避免 Next.js 静态收集时因 env var 缺失导致构建失败
let _client: SupabaseClient | null = null

function getSupabase(): SupabaseClient {
  if (_client) return _client
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_KEY
  if (!url) throw new Error("Missing env: SUPABASE_URL")
  if (!key) throw new Error("Missing env: SUPABASE_SERVICE_KEY")
  _client = createClient(url, key)
  return _client
}

// 用 Proxy 保持调用方 `supabase.from(...)` 写法不变
export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop) {
    const client = getSupabase()
    const val = (client as unknown as Record<string | symbol, unknown>)[prop]
    return typeof val === "function" ? val.bind(client) : val
  },
})

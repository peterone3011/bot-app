import { createClient } from "@supabase/supabase-js"

const url = process.env.SUPABASE_URL
const key = process.env.SUPABASE_SERVICE_KEY

if (!url) throw new Error("Missing env: SUPABASE_URL")
if (!key) throw new Error("Missing env: SUPABASE_SERVICE_KEY")

export const supabase = createClient(url, key)

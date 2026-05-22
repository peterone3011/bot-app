import { notFound } from "next/navigation"
import { supabase } from "@/lib/supabase"
import type { Message } from "@/lib/types"
import { EmbedForm } from "@/components/embed-form"

export const dynamic = "force-dynamic"

export default async function EmbedEditorPage({ params }: { params: { id: string } }) {
  const { data, error } = await supabase
    .from("messages")
    .select("*")
    .eq("id", params.id)
    .single()

  if (error || !data) notFound()

  return <EmbedForm initial={data as Message} />
}

import type { Message } from "@/lib/types"

function colorToHex(color: number | null): string {
  if (color === null) return "#5865f2"
  return `#${color.toString(16).padStart(6, "0")}`
}

export function EmbedPreview({ msg }: { msg: Partial<Message> }) {
  const borderColor = colorToHex(msg.color ?? null)

  return (
    <div
      className="rounded-md bg-[#2b2d31] p-3 w-full overflow-hidden"
      style={{ borderLeft: `4px solid ${borderColor}` }}
    >
      {msg.title && (
        <p className="font-semibold text-white text-sm mb-1 break-words">{msg.title}</p>
      )}
      {msg.description && (
        <p className="text-[#dbdee1] text-sm whitespace-pre-wrap break-words">{msg.description}</p>
      )}
      {msg.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={msg.image_url}
          alt="embed image"
          className="mt-2 max-w-full rounded"
        />
      )}
      {msg.footer && (
        <p className="mt-2 text-xs text-[#949ba4] break-words">{msg.footer}</p>
      )}
      {msg.button_label && msg.button_url && (
        <div className="mt-3">
          <a
            href={msg.button_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block rounded bg-[#5865f2] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#4752c4] transition-colors break-words"
          >
            {msg.button_label}
          </a>
        </div>
      )}
      {!msg.title && !msg.description && !msg.footer && (
        <p className="text-xs text-[#949ba4] italic">预览（填写内容后显示）</p>
      )}
    </div>
  )
}

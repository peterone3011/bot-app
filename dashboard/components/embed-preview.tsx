import type { Message } from "@/lib/types"

function colorToHex(color: number | null): string {
  if (color === null) return "#9B59B6"
  return `#${color.toString(16).padStart(6, "0")}`
}

export function EmbedPreview({ msg }: { msg: Partial<Message> }) {
  const borderColor = colorToHex(msg.color ?? null)
  const isEmpty = !msg.title && !msg.description && !msg.footer && !msg.image_url

  return (
    <div className="space-y-2">
      {/* Mini message header to set Discord context */}
      <div className="flex items-center gap-2 px-1">
        <div
          className="h-6 w-6 rounded-full"
          style={{
            background: "linear-gradient(135deg, hsl(270 45% 55%), hsl(270 45% 35%))",
            boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.08)",
          }}
          aria-hidden="true"
        />
        <div className="flex items-center gap-1.5 text-[11.5px]">
          <span className="font-semibold text-[#dbdee1]">Fortune Purple</span>
          <span className="rounded-sm bg-[#5865f2] px-1 py-px text-[9px] font-bold leading-none text-white">BOT</span>
          <span className="text-[10.5px] text-[#949ba4]">今天 14:22</span>
        </div>
      </div>

      <div
        className="rounded-[4px] bg-[#2b2d31] p-3 w-full overflow-hidden"
        style={{ borderLeft: `4px solid ${borderColor}` }}
      >
        {msg.title && (
          <p className="font-semibold text-white text-[14px] mb-1 break-words leading-snug">{msg.title}</p>
        )}
        {msg.description && (
          <p className="text-[#dbdee1] text-[13.5px] whitespace-pre-wrap break-words leading-relaxed">{msg.description}</p>
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
          <p className="mt-2 text-[11.5px] text-[#949ba4] break-words">{msg.footer}</p>
        )}
        {msg.button_label && msg.button_url && (
          <div className="mt-3">
            <a
              href={msg.button_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block rounded-[3px] bg-[#4e5058] hover:bg-[#5d5f66] px-3 py-1.5 text-[13px] font-medium text-white transition-colors break-words"
            >
              {msg.button_label}
            </a>
          </div>
        )}
        {isEmpty && (
          <p className="text-[11.5px] text-[#949ba4] italic">预览(填写内容后显示)</p>
        )}
      </div>
    </div>
  )
}

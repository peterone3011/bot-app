export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="text-center max-w-sm">
        <div
          className="fp-brand-mark mx-auto mb-5"
          style={{ width: 44, height: 44 }}
          aria-hidden="true"
        >
          <svg width="22" height="22" viewBox="0 0 16 16" fill="none">
            <path d="M8 1.5 L14.5 8 L8 14.5 L1.5 8 Z" stroke="rgba(255,255,255,0.9)" strokeWidth="1.2" strokeLinejoin="round"/>
            <path d="M8 5 L11 8 L8 11 L5 8 Z" fill="rgba(255,255,255,0.9)"/>
          </svg>
        </div>
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground/70 mb-1">Error · 404</p>
        <h1 className="text-2xl font-semibold tracking-tight">页面不存在</h1>
        <p className="mt-2 text-[13px] text-muted-foreground">你访问的路径不在管理后台中。</p>
        <a
          href="/dashboard/embeds"
          className="fp-btn-premium mt-6 inline-flex items-center justify-center gap-1.5 rounded-md px-4 h-9 text-[13px] font-medium text-white"
        >
          返回首页
        </a>
      </div>
    </div>
  )
}

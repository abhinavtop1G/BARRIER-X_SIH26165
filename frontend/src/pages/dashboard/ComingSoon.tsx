interface ComingSoonProps {
  title: string
  desc: string
}

const FEATURE_ICONS: Record<string, string> = {
  'Precursor Pattern Detection': '◌',
  'Life-Saving Rule Mapping':    '✦',
  '3D Safety Digital Twin':      '◈',
  'AI HSE Agent':                '◎',
  'Settings':                    '⚙',
}

export default function ComingSoon({ title, desc }: ComingSoonProps) {
  const icon = FEATURE_ICONS[title] ?? '⬡'

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-4">
      <div className="max-w-md w-full text-center flex flex-col items-center gap-5 p-10 bg-bx-card border border-bx-border rounded-2xl">
        <div className="text-4xl text-bx-muted opacity-40 leading-none">{icon}</div>
        <div className="inline-flex items-center gap-2 px-3 py-1 bg-white/5 border border-bx-subtle rounded-full font-mono text-[0.65rem] uppercase tracking-widest text-bx-muted">
          <span className="w-1.5 h-1.5 rounded-full bg-bx-gold opacity-80 animate-pulse" />
          Coming Soon
        </div>
        <h2 className="font-display text-2xl font-bold text-bx-text">{title}</h2>
        <p className="text-sm text-bx-secondary leading-relaxed">{desc}</p>
        <div className="w-12 h-px bg-bx-border my-1" />
        <p className="text-xs text-bx-muted italic leading-relaxed">
          This capability is on the BARRIER X roadmap and will be available in a future release.
        </p>
      </div>
    </div>
  )
}


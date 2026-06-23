'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function LoginPage() {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const router = useRouter()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw }),
    })
    if (res.ok) router.push('/')
    else setErr('ACCESS DENIED')
  }

  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-8">

        <div className="text-center space-y-3">
          <div className="font-space text-brand-gold text-3xl tracking-[0.5em] neon-gold">M3OW</div>
          <h1 className="font-play uppercase tracking-[0.4em] text-brand-white text-lg">Cat of Wall Street</h1>
          <p className="font-space text-[10px] text-brand-white/30 tracking-widest">AUTHENTICATION REQUIRED</p>
        </div>

        <div className="brand-card p-5 space-y-4">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="section-label block mb-2">ACCESS CODE</label>
              <input
                type="password"
                value={pw}
                onChange={e => setPw(e.target.value)}
                placeholder="············"
                autoComplete="current-password"
                className="w-full bg-brand-dark border border-brand-cyan/30 rounded-lg px-4 py-3 text-brand-white font-space text-sm placeholder-brand-white/15 focus:outline-none focus:border-brand-cyan/70 transition-all tracking-widest"
                style={{ caretColor: '#58E3EF' }}
              />
            </div>
            {err && (
              <p className="font-space text-[10px] text-brand-magenta tracking-widest">■ {err}</p>
            )}
            <button
              type="submit"
              className="w-full border border-brand-cyan/60 text-brand-cyan font-space text-[11px] tracking-[0.35em] uppercase py-3 rounded-lg transition-all hover:border-brand-magenta hover:text-brand-magenta active:opacity-70">
              ENTER SYSTEM
            </button>
          </form>
        </div>

        <p className="text-center font-space text-[9px] text-brand-white/15 tracking-widest">
          D3V × Ras3uCat
        </p>
      </div>
    </div>
  )
}

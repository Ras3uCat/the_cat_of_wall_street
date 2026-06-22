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
    else setErr('Wrong password')
  }

  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🐱</div>
          <h1 className="text-2xl font-bold">Cat of Wall Street</h1>
          <p className="text-slate-400 text-sm mt-1">Trading System Dashboard</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <input
            type="password"
            value={pw}
            onChange={e => setPw(e.target.value)}
            placeholder="Password"
            className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          {err && <p className="text-red-400 text-sm">{err}</p>}
          <button type="submit"
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-3 rounded-xl transition-colors">
            Enter
          </button>
        </form>
      </div>
    </div>
  )
}

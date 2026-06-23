'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function ApproveButtons({ predictionId }: { predictionId: string }) {
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  async function cancel() {
    setLoading(true)
    await fetch('/api/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: predictionId, action: 'rejected' }),
    })
    setLoading(false)
    router.refresh()
  }

  return (
    <div className="space-y-2 pt-1">
      <p className="font-space text-[10px] text-brand-gold tracking-widest text-center neon-gold">
        △ QUEUED — EXECUTES AT NEXT SESSION OPEN
      </p>
      <button
        onClick={cancel}
        disabled={loading}
        className="w-full py-3 rounded-xl border border-brand-magenta/50 text-brand-magenta font-space text-[11px] tracking-[0.3em] uppercase hover:border-brand-magenta hover:bg-brand-magenta/5 disabled:opacity-30 transition-all">
        {loading ? '···' : 'CANCEL TRADE'}
      </button>
    </div>
  )
}

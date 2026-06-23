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
    <div className="space-y-2">
      <p className="text-xs text-amber-400 text-center">Queued — executes at next local session open</p>
      <button
        onClick={cancel}
        disabled={loading}
        className="w-full py-3 rounded-xl bg-slate-700 hover:bg-slate-600 disabled:opacity-50 font-semibold text-slate-300 transition-colors">
        {loading ? '...' : 'Cancel Trade'}
      </button>
    </div>
  )
}

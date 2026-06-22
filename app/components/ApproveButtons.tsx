'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function ApproveButtons({ predictionId }: { predictionId: string }) {
  const [loading, setLoading] = useState<'approved' | 'rejected' | null>(null)
  const router = useRouter()

  async function act(action: 'approved' | 'rejected') {
    setLoading(action)
    await fetch('/api/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: predictionId, action }),
    })
    setLoading(null)
    router.refresh()
  }

  return (
    <div className="flex gap-3">
      <button
        onClick={() => act('approved')}
        disabled={loading != null}
        className="flex-1 py-3 rounded-xl bg-green-700 hover:bg-green-600 disabled:opacity-50 font-semibold text-white transition-colors">
        {loading === 'approved' ? '...' : 'APPROVE'}
      </button>
      <button
        onClick={() => act('rejected')}
        disabled={loading != null}
        className="flex-1 py-3 rounded-xl bg-red-900 hover:bg-red-800 disabled:opacity-50 font-semibold text-white transition-colors">
        {loading === 'rejected' ? '...' : 'REJECT'}
      </button>
    </div>
  )
}

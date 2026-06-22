export const runtime = 'edge'

import { NextRequest, NextResponse } from 'next/server'
import { sendEmptyPush } from '@/lib/vapid'
import { supabase } from '@/lib/supabase'

export async function POST(req: NextRequest) {
  if (req.headers.get('x-notify-secret') !== process.env.NOTIFY_SECRET) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
  }

  const { prediction_id, ticker } = await req.json()
  if (!prediction_id || !ticker) {
    return NextResponse.json({ error: 'Bad request' }, { status: 400 })
  }

  const { data: subs } = await supabase.from('push_subscriptions').select('endpoint, p256dh, auth')
  if (!subs?.length) return NextResponse.json({ sent: 0 })

  const results = await Promise.allSettled(
    subs.map((sub: { endpoint: string; p256dh: string; auth: string }) =>
      sendEmptyPush(sub, process.env.VAPID_PUBLIC_KEY!, process.env.VAPID_PRIVATE_KEY!, process.env.VAPID_SUBJECT!)
    )
  )

  const sent = results.filter(r => r.status === 'fulfilled' && (r as PromiseFulfilledResult<{ ok: boolean }>).value.ok).length
  const stale = results
    .map((r, i) => r.status === 'rejected' ? subs[i]?.endpoint : null)
    .filter(Boolean)

  if (stale.length > 0) {
    await supabase.from('push_subscriptions').delete().in('endpoint', stale)
  }

  return NextResponse.json({ sent })
}

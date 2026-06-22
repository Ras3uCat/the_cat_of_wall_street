export const runtime = 'edge'

import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

export async function POST(req: NextRequest) {
  const { id, action } = await req.json()
  if (!id || !['approved', 'rejected'].includes(action)) {
    return NextResponse.json({ error: 'Bad request' }, { status: 400 })
  }
  const fields: Record<string, string> = { approval_status: action }
  if (action === 'rejected') fields.skip_reason = 'rejected_in_app'

  const { error } = await supabase.from('predictions').update(fields).eq('id', id)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}

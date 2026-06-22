export const dynamic = 'force-dynamic'
import { NextResponse } from 'next/server'

export function GET() {
  return NextResponse.json({
    ok: true,
    env: {
      SUPABASE_URL: !!process.env.SUPABASE_URL,
      SUPABASE_SERVICE_KEY: !!process.env.SUPABASE_SERVICE_KEY,
      APP_PASSWORD: !!process.env.APP_PASSWORD,
      VAPID_PUBLIC_KEY: !!process.env.VAPID_PUBLIC_KEY,
      VAPID_PRIVATE_KEY: !!process.env.VAPID_PRIVATE_KEY,
      NOTIFY_SECRET: !!process.env.NOTIFY_SECRET,
    },
  })
}

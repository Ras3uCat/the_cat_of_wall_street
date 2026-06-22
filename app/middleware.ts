import { NextRequest, NextResponse } from 'next/server'

const PUBLIC_PATHS = ['/login', '/api/notify', '/api/subscribe', '/manifest.json', '/sw.js', '/icon-192.png', '/icon-512.png']

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl
  if (PUBLIC_PATHS.some(p => pathname.startsWith(p))) return NextResponse.next()

  const session = req.cookies.get('cws_session')?.value
  if (session !== process.env.APP_PASSWORD) {
    return NextResponse.redirect(new URL('/login', req.url))
  }
  return NextResponse.next()
}

export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] }

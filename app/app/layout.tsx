import type { Metadata, Viewport } from 'next'
import './globals.css'
import BottomNav from '@/components/BottomNav'
import SwRegister from '@/components/SwRegister'

export const metadata: Metadata = {
  title: 'Cat of Wall Street',
  description: 'AI trading system dashboard',
  manifest: '/manifest.json',
  appleWebApp: { capable: true, statusBarStyle: 'black-translucent', title: 'CatWS' },
}

export const viewport: Viewport = {
  themeColor: '#0f172a',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-900 text-slate-100 pb-20">
        <main className="min-h-dvh">{children}</main>
        <BottomNav />
        <SwRegister />
      </body>
    </html>
  )
}

import type { Metadata, Viewport } from 'next'
import { Inter, Play, Orbitron, Space_Grotesk } from 'next/font/google'
import './globals.css'
import BottomNav from '@/components/BottomNav'
import SwRegister from '@/components/SwRegister'

const inter        = Inter({ subsets: ['latin'], variable: '--font-inter',    display: 'swap' })
const play         = Play({ subsets: ['latin'], weight: ['400', '700'], variable: '--font-play', display: 'swap' })
const orbitron     = Orbitron({ subsets: ['latin'], variable: '--font-orbitron', display: 'swap' })
const spaceGrotesk = Space_Grotesk({ subsets: ['latin'], variable: '--font-space', display: 'swap' })

export const metadata: Metadata = {
  title: 'Cat of Wall Street',
  description: 'AI trading system dashboard',
  manifest: '/manifest.json',
  appleWebApp: { capable: true, statusBarStyle: 'black-translucent', title: 'CatWS' },
}

export const viewport: Viewport = {
  themeColor: '#000612',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${play.variable} ${orbitron.variable} ${spaceGrotesk.variable}`}>
      <body className="bg-brand-dark text-brand-white pb-20">
        <header className="sticky top-0 z-50 bg-brand-dark/95 backdrop-blur-sm border-b border-brand-cyan/10">
          <div className="flex items-center justify-between px-4 h-10">
            <span className="font-play uppercase tracking-[0.35em] text-brand-white/60 text-[10px]">
              CAT OF WALL ST
            </span>
            <span className="font-space text-[11px] text-brand-gold tracking-widest neon-gold">M3OW</span>
          </div>
        </header>
        <main className="min-h-dvh">{children}</main>
        <BottomNav />
        <SwRegister />
      </body>
    </html>
  )
}

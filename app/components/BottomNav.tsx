'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  { href: '/',            label: 'Home',    icon: '📊' },
  { href: '/predictions', label: 'Trades',  icon: '📋' },
  { href: '/approvals',   label: 'Approve', icon: '✅' },
  { href: '/performance', label: 'Stats',   icon: '📈' },
  { href: '/positions',   label: 'Holdings',icon: '💼' },
]

export default function BottomNav() {
  const path = usePathname()
  if (path === '/login') return null
  return (
    <nav className="fixed bottom-0 left-0 right-0 max-w-[480px] mx-auto bg-slate-800 border-t border-slate-700 flex">
      {NAV.map(({ href, label, icon }) => {
        const active = path === href || (href !== '/' && path.startsWith(href))
        return (
          <Link key={href} href={href}
            className={`flex-1 flex flex-col items-center py-2 text-xs gap-0.5 transition-colors
              ${active ? 'text-blue-400' : 'text-slate-400'}`}>
            <span className="text-lg leading-none">{icon}</span>
            {label}
          </Link>
        )
      })}
    </nav>
  )
}

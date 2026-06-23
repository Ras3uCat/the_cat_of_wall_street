'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  { href: '/',            label: 'HOME'   },
  { href: '/predictions', label: 'TRADES' },
  { href: '/approvals',   label: 'QUEUE'  },
  { href: '/performance', label: 'STATS'  },
  { href: '/positions',   label: 'HOLD'   },
]

export default function BottomNav() {
  const path = usePathname()
  if (path === '/login') return null
  return (
    <nav className="fixed bottom-0 left-0 right-0 max-w-[480px] mx-auto bg-brand-dark/95 backdrop-blur-sm border-t border-brand-cyan/20 flex">
      {NAV.map(({ href, label }) => {
        const active = path === href || (href !== '/' && path.startsWith(href))
        return (
          <Link key={href} href={href}
            className={`flex-1 flex flex-col items-center gap-1 py-3 font-space text-[9px] tracking-widest transition-all
              ${active ? 'text-brand-cyan neon-text' : 'text-brand-white/25 hover:text-brand-white/50'}`}>
            <span className={`block w-1 h-1 rounded-full transition-all ${active ? 'bg-brand-cyan' : 'bg-transparent'}`}
              style={active ? {boxShadow: '0 0 4px #58E3EF'} : undefined} />
            {label}
          </Link>
        )
      })}
    </nav>
  )
}

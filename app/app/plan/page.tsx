export default function PlanPage() {
  return (
    <div className="p-4 space-y-4 max-w-[480px] mx-auto pb-8">
      <h1 className="text-xl font-bold pt-2">System Rules</h1>

      <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
        <h2 className="text-sm font-semibold text-blue-400">Confidence Thresholds</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-xs text-left border-b border-slate-700">
              <th className="pb-2">VIX Regime</th><th className="pb-2">VIX Range</th><th className="pb-2">Min Score</th>
            </tr>
          </thead>
          <tbody className="space-y-1">
            {[
              ['Low', '< 15', '60'],
              ['Normal', '15–20', '60'],
              ['Elevated', '20–30', '65'],
              ['High', '> 30', '72'],
            ].map(([regime, range, score]) => (
              <tr key={regime} className="border-b border-slate-700/50">
                <td className="py-1.5 text-slate-300">{regime}</td>
                <td className="py-1.5 text-slate-400">{range}</td>
                <td className="py-1.5 font-semibold">{score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
        <h2 className="text-sm font-semibold text-blue-400">After-Tax Minimums (30% rate)</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-xs text-left border-b border-slate-700">
              <th className="pb-2">Timeframe</th><th className="pb-2">Net After-Tax</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Intraday (0–1d)', '+3%'],
              ['Short-term (4–30d)', '+5%'],
              ['Medium-term (30–90d)', '+7%'],
            ].map(([tf, min]) => (
              <tr key={tf} className="border-b border-slate-700/50">
                <td className="py-1.5 text-slate-300">{tf}</td>
                <td className="py-1.5 text-green-400 font-semibold">{min}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
        <h2 className="text-sm font-semibold text-blue-400">Risk Hard Rules</h2>
        <ul className="space-y-2 text-sm text-slate-300">
          <li className="flex gap-2"><span className="text-red-400 shrink-0">■</span>Max 2 new positions/day</li>
          <li className="flex gap-2"><span className="text-red-400 shrink-0">■</span>Max 20% equity deployed per session</li>
          <li className="flex gap-2"><span className="text-red-400 shrink-0">■</span>Agentic account only (cash, T+1 settlement)</li>
          <li className="flex gap-2"><span className="text-red-400 shrink-0">■</span>Stop loss: 7% below entry (standard), 5% below (elevated VIX)</li>
          <li className="flex gap-2"><span className="text-red-400 shrink-0">■</span>No trades when macro_go = false</li>
          <li className="flex gap-2"><span className="text-red-400 shrink-0">■</span>Manual APPROVE required before any execution</li>
        </ul>
      </section>

      <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
        <h2 className="text-sm font-semibold text-blue-400">Trailing Stop Ladder</h2>
        <ul className="space-y-2 text-sm text-slate-300">
          <li className="flex gap-2"><span className="text-green-400 shrink-0">+15%</span>Move stop to breakeven</li>
          <li className="flex gap-2"><span className="text-green-400 shrink-0">+25%</span>Trail 10% below peak</li>
          <li className="flex gap-2"><span className="text-green-400 shrink-0">+35%</span>Trail 8% below peak</li>
        </ul>
      </section>

      <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
        <h2 className="text-sm font-semibold text-blue-400">Exit Triggers</h2>
        <ul className="space-y-2 text-sm text-slate-300">
          {[
            'Stop loss hit',
            'Price target reached → review whether to hold',
            'Timeframe expired',
            'Original thesis invalidated (earnings miss, guidance cut, etc.)',
            'Trailing stop triggered',
            'Sector rotation turns against position',
            'Manual exit (your call)',
          ].map((trigger, i) => (
            <li key={i} className="flex gap-2"><span className="text-slate-500 shrink-0">{i + 1}.</span>{trigger}</li>
          ))}
        </ul>
      </section>

      <section className="bg-slate-800 rounded-2xl p-4 space-y-2">
        <h2 className="text-sm font-semibold text-blue-400">Learning Period</h2>
        <p className="text-sm text-slate-300">No trade execution through 2026-06-28. Debates and prediction logging run normally to build calibration data.</p>
      </section>
    </div>
  )
}

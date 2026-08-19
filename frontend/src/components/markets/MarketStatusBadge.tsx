import { useEffect, useState } from 'react'

interface SessionWindow {
  label:      string
  timeZone:   string
  openHour:   number
  openMinute: number
  closeHour:  number
  closeMinute: number
}

// İK-09: BIST seansı ~10:00-18:00 (İstanbul saati, hafta içi)
// İK-10: ABD seansı 09:30-16:00 (ABD Doğu Saati) — Intl API DST'yi otomatik hesaplar
const SESSIONS: SessionWindow[] = [
  { label: 'BIST', timeZone: 'Europe/Istanbul',    openHour: 10, openMinute: 0,  closeHour: 18, closeMinute: 0 },
  { label: 'ABD',  timeZone: 'America/New_York',   openHour: 9,  openMinute: 30, closeHour: 16, closeMinute: 0 },
]

function isSessionOpen(session: SessionWindow, now: Date): boolean {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: session.timeZone,
    weekday: 'short',
    hour: 'numeric',
    minute: 'numeric',
    hourCycle: 'h23',
  }).formatToParts(now)

  const weekday = parts.find((p) => p.type === 'weekday')?.value ?? ''
  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? 0)
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? 0)

  const isWeekday = !['Sat', 'Sun'].includes(weekday)
  const minutesNow = hour * 60 + minute
  const minutesOpen = session.openHour * 60 + session.openMinute
  const minutesClose = session.closeHour * 60 + session.closeMinute

  return isWeekday && minutesNow >= minutesOpen && minutesNow < minutesClose
}

/**
 * BIST ve ABD piyasa seanslarının anlık açık/kapalı durumunu gösteren rozet grubu.
 * Seans saatleri İK-09 (BIST) ve İK-10 (ABD, Türkiye saatine göre) iş kuralına dayanır.
 */
export default function MarketStatusBadge() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex items-center gap-2">
      {SESSIONS.map((session) => {
        const open = isSessionOpen(session, now)
        return (
          <span
            key={session.label}
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              open ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-slate-800/5 text-slate-400 border border-white/10'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${open ? 'bg-emerald-500' : 'bg-slate-400'}`} />
            {session.label} {open ? 'Açık' : 'Kapalı'}
          </span>
        )
      })}
    </div>
  )
}

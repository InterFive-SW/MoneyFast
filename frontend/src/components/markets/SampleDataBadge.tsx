/**
 * Marks a screen whose numbers are illustrative rather than live.
 *
 * Some of the markets screens have no data source and cannot get one from the
 * current stack: TEFAS publishes no feed we can read for mutual funds, and
 * yfinance carries no BIST index constituents, earnings calendar, IPO
 * schedule, analyst ratings or capital-increase notices.
 *
 * The alternative to this badge was deleting those screens. Keeping them
 * unlabelled was never an option: sample figures sitting beside a live ticker
 * read as real, and someone would eventually act on one.
 */
export default function SampleDataBadge({ reason }: { reason: string }) {
  return (
    <div className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4">
      <svg
        className="mt-0.5 h-4 w-4 shrink-0 text-amber-500"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      <p className="text-sm leading-relaxed text-amber-200/90">
        <span className="font-semibold">Örnek veri.</span> Bu ekrandaki rakamlar
        gerçek piyasa verisi değildir, yalnızca arayüzü göstermek içindir. {reason}
      </p>
    </div>
  )
}

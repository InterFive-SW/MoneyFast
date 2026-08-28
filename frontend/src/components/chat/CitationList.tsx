import { useId, useState } from 'react'
import {
  CITATION_INITIAL_VISIBLE,
  formatCitationTime,
  type SafeResearchCitation,
  sourceTypeLabel,
  verificationLabel,
} from '../../lib/researchCitations'

interface CitationListProps {
  citations: SafeResearchCitation[]
}

/**
 * Compact "Kaynaklar" footnote under an assistant bubble.
 *
 * KAP disclosures are the primary outbound link when present; the X post is
 * always labeled as a social signal, never as an official filing.
 */
export default function CitationList({ citations }: CitationListProps) {
  const headingId = useId()
  const [expanded, setExpanded] = useState(false)

  if (!citations.length) return null

  const visible = expanded
    ? citations
    : citations.slice(0, CITATION_INITIAL_VISIBLE)
  const hiddenCount = citations.length - visible.length

  return (
    <section
      className="mt-2 pt-2 border-t border-white/10 flex flex-col gap-2"
      aria-labelledby={headingId}
    >
      <h3 id={headingId} className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        Kaynaklar
      </h3>
      <ul className="flex flex-col gap-2 m-0 p-0 list-none">
        {visible.map((citation) => (
          <CitationItem key={citation.evidence_id} citation={citation} />
        ))}
      </ul>
      {hiddenCount > 0 && (
        <button
          type="button"
          className="self-start text-[10px] text-brandBlue hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brandBlue/60 rounded"
          aria-expanded={expanded}
          onClick={() => setExpanded(true)}
        >
          {hiddenCount} kaynak daha göster
        </button>
      )}
      {expanded && citations.length > CITATION_INITIAL_VISIBLE && (
        <button
          type="button"
          className="self-start text-[10px] text-slate-400 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brandBlue/60 rounded"
          aria-expanded={expanded}
          onClick={() => setExpanded(false)}
        >
          Daha az göster
        </button>
      )}
      <p className="text-[10px] leading-snug text-slate-500">
        Sosyal sinyaller araştırma desteğidir; doğrulama durumu tek başına
        yatırım tavsiyesi anlamına gelmez.
      </p>
    </section>
  )
}

function CitationItem({ citation }: { citation: SafeResearchCitation }) {
  const title =
    citation.displayName?.trim() ||
    `@${citation.handle}`
  const when = formatCitationTime(citation.publishedAt)
  const verification = verificationLabel(citation.verificationStatus)
  const source = sourceTypeLabel(citation.sourceType)
  const primaryIsKap = Boolean(citation.kapUrl)

  return (
    <li className="flex flex-col gap-1 min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 min-w-0">
        <span className="text-[11px] text-slate-200 font-medium truncate max-w-full">
          {title}
        </span>
        <span className="text-[10px] text-slate-400 truncate">@{citation.handle}</span>
        {when && (
          <time
            className="text-[10px] text-slate-500"
            dateTime={
              citation.publishedAt instanceof Date
                ? citation.publishedAt.toISOString()
                : undefined
            }
          >
            {when}
          </time>
        )}
      </div>

      {(verification || source) && (
        <div className="flex flex-wrap gap-1">
          {verification && (
            <span className="text-[10px] leading-none px-1.5 py-0.5 rounded bg-white/10 text-slate-300">
              {verification}
            </span>
          )}
          {source && (
            <span className="text-[10px] leading-none px-1.5 py-0.5 rounded bg-white/5 text-slate-400">
              {source}
            </span>
          )}
        </div>
      )}

      {citation.matchedSymbols.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {citation.matchedSymbols.map((symbol) => (
            <span
              key={symbol}
              className="text-[10px] leading-none px-1.5 py-0.5 rounded bg-white/10 text-slate-300"
            >
              {symbol}
            </span>
          ))}
        </div>
      )}

      {citation.excerpt && (
        <p className="text-[10px] leading-snug text-slate-400 break-words">
          {citation.excerpt}
        </p>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {primaryIsKap && citation.kapUrl && (
          <a
            href={citation.kapUrl}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="text-[10px] text-brandBlue hover:underline break-all"
          >
            KAP bildirimini görüntüle
          </a>
        )}
        {citation.postUrl && (
          <a
            href={citation.postUrl}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="text-[10px] text-slate-300 hover:underline break-all"
          >
            {primaryIsKap ? 'X gönderisini gör (sosyal sinyal)' : 'X gönderisini gör'}
          </a>
        )}
        {!primaryIsKap && !citation.postUrl && citation.kapUrl && (
          <a
            href={citation.kapUrl}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="text-[10px] text-brandBlue hover:underline break-all"
          >
            KAP bildirimini görüntüle
          </a>
        )}
      </div>
    </li>
  )
}

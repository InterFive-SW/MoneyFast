/**
 * Market-research citation helpers.
 *
 * Backend already validates citations, but the browser is a second trust
 * boundary: a compromised or stale intermediary must not turn a look-alike
 * host into a clickable "source". This module never invents citations from
 * assistant prose — it only filters and normalizes structured payloads.
 */

export type ResearchPlatform = 'x'
export type ResearchVerificationStatus =
  | 'unverified'
  | 'corroborated'
  | 'officially_verified'
  | 'contradicted'
export type ResearchSourceType =
  | 'official_company'
  | 'official_disclosure'
  | 'disclosure_aggregator'
  | 'news_agency'
  | 'financial_media'
  | 'analyst'

export interface ResearchCitation {
  evidence_id: string
  platform: ResearchPlatform
  handle: string
  display_name?: string | null
  published_at?: string | null
  post_url: string
  kap_url?: string | null
  verification_status?: ResearchVerificationStatus | null
  source_type?: ResearchSourceType | null
  excerpt?: string | null
  matched_symbols?: string[]
}

/** Safe, render-ready citation after frontend validation. */
export interface SafeResearchCitation {
  evidence_id: string
  platform: ResearchPlatform
  handle: string
  displayName: string | null
  publishedAt: Date | null
  /** Validated HTTPS X status URL, or null when unusable. */
  postUrl: string | null
  /** Validated HTTPS KAP URL, or null when absent/unusable. */
  kapUrl: string | null
  verificationStatus: ResearchVerificationStatus | null
  sourceType: ResearchSourceType | null
  excerpt: string | null
  matchedSymbols: string[]
}

const EVIDENCE_ID_RE = /^[a-f0-9]{32}$/
const HANDLE_RE = /^[A-Za-z0-9_]{1,50}$/
const X_HOSTS = new Set(['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'])
const KAP_HOSTS = new Set(['kap.org.tr', 'www.kap.org.tr'])
const VERIFICATION = new Set<ResearchVerificationStatus>([
  'unverified',
  'corroborated',
  'officially_verified',
  'contradicted',
])
const SOURCE_TYPES = new Set<ResearchSourceType>([
  'official_company',
  'official_disclosure',
  'disclosure_aggregator',
  'news_agency',
  'financial_media',
  'analyst',
])
// Every C0 control (incl. TAB/LF/CR) plus DEL. Checked on the *raw* string
// before trim/URL parse — JS's URL parser silently strips TAB/LF/CR, which
// would otherwise turn "sta\ttus" into an accepted path.
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/
const X_PATH_RE = /^\/[A-Za-z0-9_]+\/status\/[0-9]+\/?$/

const INITIAL_VISIBLE = 3

export const CITATION_INITIAL_VISIBLE = INITIAL_VISIBLE

function hasControlChars(value: string): boolean {
  return CONTROL_CHARS.test(value)
}

function parseHttpsUrl(raw: unknown): URL | null {
  if (typeof raw !== 'string') return null
  // Fail closed on controls *before* trim/parse — never repair them away.
  if (hasControlChars(raw)) return null
  if (!raw.trim()) return null
  let parsed: URL
  try {
    parsed = new URL(raw.trim())
  } catch {
    return null
  }
  if (parsed.protocol !== 'https:') return null
  if (parsed.username || parsed.password) return null
  if (parsed.port && parsed.port !== '443') return null
  return parsed
}

/** True only for canonical HTTPS X/Twitter status URLs. */
export function isSafeXPostUrl(raw: unknown): boolean {
  const parsed = parseHttpsUrl(raw)
  if (!parsed) return false
  const host = parsed.hostname.toLowerCase()
  if (!X_HOSTS.has(host)) return false
  if (parsed.search || parsed.hash) return false
  return X_PATH_RE.test(parsed.pathname)
}

/** True only for HTTPS KAP disclosure URLs on the exact allowed hosts. */
export function isSafeKapUrl(raw: unknown): boolean {
  const parsed = parseHttpsUrl(raw)
  if (!parsed) return false
  return KAP_HOSTS.has(parsed.hostname.toLowerCase())
}

function asVerification(value: unknown): ResearchVerificationStatus | null {
  return typeof value === 'string' && VERIFICATION.has(value as ResearchVerificationStatus)
    ? (value as ResearchVerificationStatus)
    : null
}

function asSourceType(value: unknown): ResearchSourceType | null {
  return typeof value === 'string' && SOURCE_TYPES.has(value as ResearchSourceType)
    ? (value as ResearchSourceType)
    : null
}

function parsePublishedAt(value: unknown): Date | null {
  if (value == null || value === '') return null
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value
  }
  if (typeof value !== 'string' || hasControlChars(value)) return null
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return null
  // Reject timezone-naive ISO strings (no offset / Z).
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value.trim())) return null
  return new Date(ms)
}

function normalizeSymbols(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const item of value) {
    if (typeof item !== 'string' || !item.trim()) continue
    if (item.trim().length > 16) continue
    const symbol = item.trim().toUpperCase()
    if (seen.has(symbol)) continue
    seen.add(symbol)
    out.push(symbol)
    if (out.length >= 8) break
  }
  return out
}

function normalizeExcerpt(value: unknown): string | null {
  if (value == null) return null
  if (typeof value !== 'string') return null
  // Controls checked on the original — whitespace-only after trim is separate.
  if (hasControlChars(value) || value.includes('```')) return null
  const trimmed = value.trim()
  if (!trimmed || trimmed.length > 280) return null
  return trimmed
}

function normalizeDisplayName(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null
  if (hasControlChars(value)) return null
  return value.trim().slice(0, 120)
}

/**
 * Map either the API (snake_case) shape or a JSON-revived SafeResearchCitation
 * (camelCase, publishedAt as ISO string or Date) onto the wire fields
 * sanitizeCitation understands. Never casts blindly to SafeResearchCitation.
 */
export function citationToWire(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object') return raw
  const row = raw as Record<string, unknown>

  const publishedRaw = row.published_at ?? row.publishedAt
  let published_at: string | null = null
  if (publishedRaw instanceof Date) {
    published_at = Number.isNaN(publishedRaw.getTime())
      ? null
      : publishedRaw.toISOString()
  } else if (typeof publishedRaw === 'string') {
    published_at = publishedRaw
  }

  // Storage camelCase uses postUrl/kapUrl; API uses post_url/kap_url.
  const looksStored =
    'postUrl' in row ||
    'kapUrl' in row ||
    'displayName' in row ||
    'publishedAt' in row ||
    'matchedSymbols' in row ||
    'verificationStatus' in row ||
    'sourceType' in row

  if (!looksStored) {
    // published_at already reflects row.published_at / publishedAt when those
    // were strings or Dates; non-temporal values stay null (fail closed).
    return {
      ...row,
      published_at,
    }
  }

  return {
    evidence_id: row.evidence_id,
    platform: row.platform,
    handle: row.handle,
    display_name: row.displayName ?? row.display_name ?? null,
    published_at,
    post_url: row.postUrl ?? row.post_url,
    kap_url: row.kapUrl ?? row.kap_url ?? null,
    verification_status: row.verificationStatus ?? row.verification_status ?? null,
    source_type: row.sourceType ?? row.source_type ?? null,
    excerpt: row.excerpt ?? null,
    matched_symbols: row.matchedSymbols ?? row.matched_symbols ?? [],
  }
}

/**
 * Project one unknown API object onto a safe citation, or null when it cannot
 * be shown without risking a bad link or broken bubble.
 */
export function sanitizeCitation(raw: unknown): SafeResearchCitation | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>

  const evidenceId = typeof row.evidence_id === 'string' ? row.evidence_id : ''
  if (hasControlChars(evidenceId) || !EVIDENCE_ID_RE.test(evidenceId)) return null

  if (row.platform !== 'x') return null

  const handleRaw = typeof row.handle === 'string' ? row.handle : ''
  if (hasControlChars(handleRaw)) return null
  const handle = handleRaw.replace(/^@/, '').trim()
  if (!HANDLE_RE.test(handle)) return null

  const postUrl = isSafeXPostUrl(row.post_url) ? String(row.post_url).trim() : null
  const kapUrl =
    row.kap_url == null || row.kap_url === ''
      ? null
      : isSafeKapUrl(row.kap_url)
        ? String(row.kap_url).trim()
        : null

  // Need at least one safe outbound link; otherwise the entry is useless and
  // would only pretend to cite a source.
  if (!postUrl && !kapUrl) return null

  return {
    evidence_id: evidenceId,
    platform: 'x',
    handle,
    displayName: normalizeDisplayName(row.display_name),
    publishedAt: parsePublishedAt(row.published_at),
    postUrl,
    kapUrl,
    verificationStatus: asVerification(row.verification_status),
    sourceType: asSourceType(row.source_type),
    excerpt: normalizeExcerpt(row.excerpt),
    matchedSymbols: normalizeSymbols(row.matched_symbols),
  }
}

/**
 * Normalize a chat-response `citations` field.
 *
 * Missing / null / non-array → []. Duplicates keep the first evidence_id.
 * Order preserved. Never fabricates entries from free text.
 */
export function normalizeCitations(raw: unknown): SafeResearchCitation[] {
  if (raw == null) return []
  if (!Array.isArray(raw)) return []
  const out: SafeResearchCitation[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    const safe = sanitizeCitation(item)
    if (!safe) continue
    if (seen.has(safe.evidence_id)) continue
    seen.add(safe.evidence_id)
    out.push(safe)
  }
  return out
}

/**
 * Fail-closed revive for citations loaded from localStorage (or any untrusted
 * JSON). Revalidates URLs/fields; never casts stored objects to SafeResearchCitation.
 */
export function reviveCitations(raw: unknown): SafeResearchCitation[] {
  if (raw == null) return []
  if (!Array.isArray(raw)) return []
  return normalizeCitations(raw.map(citationToWire))
}

export function verificationLabel(
  status: ResearchVerificationStatus | null,
): string | null {
  switch (status) {
    case 'officially_verified':
      return 'Resmi doğrulanmış'
    case 'corroborated':
      return 'Desteklenmiş'
    case 'contradicted':
      return 'Çelişkili'
    case 'unverified':
      return 'Doğrulanmamış'
    default:
      return null
  }
}

export function sourceTypeLabel(sourceType: ResearchSourceType | null): string | null {
  switch (sourceType) {
    case 'official_company':
      return 'Şirket hesabı'
    case 'official_disclosure':
      return 'Resmi bildirim'
    case 'disclosure_aggregator':
      return 'Bildirim derleyicisi'
    case 'news_agency':
      return 'Ajans'
    case 'financial_media':
      return 'Finans medyası'
    case 'analyst':
      return 'Analist'
    default:
      return null
  }
}

export function formatCitationTime(value: Date | null, locale = 'tr-TR'): string | null {
  // Guard against a string sneaking through a bad revive path — never call
  // .getTime() on a non-Date.
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return null
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(value)
  } catch {
    return null
  }
}

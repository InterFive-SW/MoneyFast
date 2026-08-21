/**
 * Editorial sector groupings — a product decision, not market data.
 *
 * These are curated themes, not something a provider publishes, so they are
 * configuration rather than sample data. They lived in `mockData.ts`, which
 * made a legitimate config import look like a dependency on fabricated prices.
 *
 * The symbols are real and resolve against /api/market/instruments; only the
 * grouping is ours.
 */

export interface CustomSectorGroup {
  name:        string
  description: string
  symbols:     string[]
}

/**
 * BIST'in resmî sınıflandırmasını kullanmayan, birlikte hareket eden şirketleri
 * gruplayan özel segmentasyon örnekleri — Sektörler ekranının Fintables'tan
 * farklılaştığı nokta budur.
 */
export const CUSTOM_SECTOR_GROUPS: CustomSectorGroup[] = [
  { name: 'Savunma & Havacılık (Özel Grup)', symbols: ['ASELS', 'THYAO'],
    description: 'Resmî BIST sınıflandırmasında ayrı sektörlerde (Savunma / Ulaştırma) yer alsa da savunma-havacılık haber akışında birlikte hareket eden şirketler.' },
  { name: 'Emtia Fiyatına Duyarlı (Özel Grup)', symbols: ['TUPRS', 'SASA', 'EREGL'],
    description: 'Farklı resmî sektörlerde (Enerji, Kimya, Sanayi) olsa da küresel emtia fiyatlarındaki dalgalanmalardan benzer şekilde etkilenen şirketler.' },
]

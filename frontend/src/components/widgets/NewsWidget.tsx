import { useState } from 'react'
import type { NewsItem } from '../../api/client'

interface Props {
  news: NewsItem[]
}

/**
 * Haberler Bileşeni
 * Piyasa haberlerini filtrelenebilir yapıda sunar.
 */
export default function NewsWidget({ news }: Props) {
  const [filter, setFilter] = useState<'Tümü' | 'Piyasa Haberleri' | 'KAP Bildirimleri' | 'BIST' | 'ABD' | 'Genel'>('Tümü')

  const filteredNews = filter === 'Tümü' ? news : news.filter(n => n.category === filter)

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Piyasa Haberleri</h3>
        
        <div className="flex space-x-1 bg-slate-100/50 p-1 rounded-lg">
          {['Tümü', 'Piyasa Haberleri', 'KAP Bildirimleri'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f as any)}
              className={`px-2 py-1 text-[10px] uppercase tracking-wider font-semibold rounded-md transition-colors ${
                filter === f ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {f === 'Piyasa Haberleri' ? 'Piyasa' : f === 'KAP Bildirimleri' ? 'KAP' : f}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 -mr-2 space-y-4">
        {filteredNews.map((item) => (
          <div key={item.id} className="group cursor-pointer">
            <div className="flex items-start justify-between">
              <h4 className="text-sm font-semibold text-slate-800 group-hover:text-emerald-600 transition-colors line-clamp-2 pr-4">
                {item.title}
              </h4>
              <span className="text-[10px] font-medium text-slate-400 whitespace-nowrap mt-0.5">{item.time}</span>
            </div>
            <div className="flex items-center mt-1.5 space-x-2">
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">{item.source}</span>
              <span className="w-1 h-1 rounded-full bg-slate-300"></span>
              <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                {item.category}
              </span>
            </div>
          </div>
        ))}
        {filteredNews.length === 0 && (
          <div className="text-sm text-slate-500 py-4 text-center">Bu kategoride haber bulunamadı.</div>
        )}
      </div>
    </div>
  )
}

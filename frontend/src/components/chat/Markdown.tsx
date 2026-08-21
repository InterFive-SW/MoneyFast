import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

/**
 * Asistan metnini markdown olarak render eder.
 *
 * Metin ham olarak bir `<p>` içine basılıyordu; ajan ise markdown üretiyor.
 * Sonuç, kullanıcının ekranında düz metin olarak görünen `**kalın**`
 * yıldızları ve tablo yerine boru işaretleriyle dolu satırlardı.
 *
 * GFM eklidir çünkü piyasa verisi ajanı boru işaretli tablolar yazıyor;
 * onsuz tablolar tek satıra çökerdi.
 *
 * HAM HTML RENDER EDİLMEZ. `react-markdown` varsayılan olarak HTML'i
 * yok sayar ve `rehype-raw` bilerek eklenmemiştir: buradaki metin model
 * çıktısıdır ve bir kısmı RAG ile getirilen belgelerden türer, yani
 * güvenilmez girdidir.
 */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="mf-markdown text-[15px] leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {text}
      </ReactMarkdown>
    </div>
  )
}

const COMPONENTS: Components = {
  // Kaynak bağlantıları yeni sekmede açılır. `noopener` olmadan hedef sayfa
  // `window.opener` üzerinden bu sekmeyi yönlendirebilir; bağlantıların
  // kaynağı model çıktısı olduğu için bu varsayılan kabul edilemez.
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="text-brandBlue underline decoration-brandBlue/40 underline-offset-2 hover:decoration-brandBlue"
    >
      {children}
    </a>
  ),
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  h1: ({ children }) => <h3 className="mb-2 mt-1 text-base font-semibold text-white">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-2 mt-1 text-base font-semibold text-white">{children}</h3>,
  h3: ({ children }) => <h3 className="mb-1 mt-1 text-sm font-semibold text-white">{children}</h3>,
  code: ({ children }) => (
    <code className="rounded bg-black/30 px-1 py-0.5 font-mono text-[13px]">{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-white/20 pl-3 text-slate-300">{children}</blockquote>
  ),
  // Tablo kendi içinde yatay kayar. Aksi halde on kolonlu bir fiyat tablosu
  // sohbet balonunu ve onunla birlikte sayfayı yana taşırdı.
  table: ({ children }) => (
    <div className="my-2 -mx-1 overflow-x-auto">
      <table className="w-full border-collapse text-[13px] tabular-nums">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-white/15 px-2 py-1.5 text-left font-semibold text-slate-300 whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-white/5 px-2 py-1.5 align-top">{children}</td>
  ),
}

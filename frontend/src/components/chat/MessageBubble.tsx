// src/components/chat/MessageBubble.tsx
import { ChatMessage, ChartWidgetPayload, ActionWidgetPayload, PortfolioWidgetPayload } from '../../types/chat';
import ChartWidget from './widgets/ChartWidget';
import ActionWidget from './widgets/ActionWidget';
import PortfolioWidget from './widgets/PortfolioWidget';
import Markdown from './Markdown';
import { useTypewriter } from '../../hooks/useTypewriter';

interface MessageBubbleProps {
  message: ChatMessage;
  /** Metni yazılıyormuş gibi ortaya çıkarır. Sadece son yanıt için. */
  animate?: boolean;
}

/**
 * MessageBubble Bileşeni
 * 
 * Kullanıcı ve yapay zeka mesajlarının arayüzdeki temsilidir.
 * Mesaj tipine göre farklı stiller uygulanır ve widget varsa render edilir.
 */
export default function MessageBubble({ message, animate = false }: MessageBubbleProps) {
  const isUser = message.sender === 'user';
  // Yalnızca son asistan mesajı yazılır. Geçmiş mesajlar her render'da
  // yeniden yazılsaydı, sohbet her açılışta baştan canlanırdı.
  const shownText = useTypewriter(message.text, animate && !isUser);
  
  // Saati formatla (HH:mm)
  const timeString = message.timestamp.toLocaleTimeString('tr-TR', {
    hour: '2-digit',
    minute: '2-digit'
  });

  return (
    <div className={`flex w-full my-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[85%] md:max-w-[75%] gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        
        {/* Yapay Zeka Avatarı */}
        {!isUser && (
          <div className="w-8 h-8 rounded-full bg-brandBlue/20 flex items-center justify-center text-brandBlue font-bold text-xs shrink-0 mt-auto mb-1">
            MF
          </div>
        )}

        {/* Mesaj İçeriği */}
        <div 
          className={`flex flex-col px-4 py-3 ${
            isUser 
              // Kendi seçim rengi. Uygulama genelinde seçim `bg-brandBlue`
              // (bkz. DashboardLayout) ve bu balonun ZEMİNİ de brandBlue —
              // yani kullanıcının kendi mesajı seçilebiliyordu ama vurgusu
              // zeminle aynı renk olduğu için hiçbir şey olmuyormuş gibi
              // görünüyordu.
              ? 'bg-brandBlue text-white shadow-md rounded-2xl rounded-br-sm selection:bg-white selection:text-brandBlue' 
              : 'bg-slate-800/80 backdrop-blur-md border border-white/10 text-white shadow-xl rounded-2xl rounded-bl-sm'
          }`}
        >
          {/* Kullanıcının kendi metni yazdığı gibi durur; markdown olarak
              yorumlamak yazdıklarını değiştirmek olurdu. Asistan ise
              markdown üretiyor ve ham basıldığında ekranda yıldızlar ve boru
              işaretleri görünüyordu. */}
          {isUser ? (
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap">{message.text}</p>
          ) : (
            <Markdown text={shownText} />
          )}
          
          {/* Widget Render Alanı */}
          {message.widget && message.widget.type === 'chart' && (
            <ChartWidget payload={message.widget.payload as ChartWidgetPayload} />
          )}
          {message.widget && message.widget.type === 'action' && (
            <ActionWidget payload={message.widget.payload as ActionWidgetPayload} />
          )}
          {message.widget && message.widget.type === 'portfolio' && (
            <PortfolioWidget payload={message.widget.payload as PortfolioWidgetPayload} />
          )}

          {/*
            Yasal bildirimler — kelimesi kelimesine, ama gövde metninin
            parçası değil. Her cevabın sonuna yapıştırılan kalıp metin,
            okuyucuyu bildirimi gerçekten önemli olduğu yerde de atlamaya
            alıştırıyordu. Burada görünür ama cevabı boğmuyor.
          */}
          {!isUser && message.disclosures && message.disclosures.length > 0 && (
            <div className="mt-2 pt-2 border-t border-white/10 flex flex-col gap-1">
              {message.disclosures.map((notice) => (
                <p key={notice} className="text-[10px] leading-snug text-slate-400">
                  {notice}
                </p>
              ))}
            </div>
          )}

          <span 
            className={`text-[10px] mt-1 ${
              isUser ? 'text-blue-200 self-end' : 'text-slate-400 self-start'
            }`}
          >
            {timeString}
          </span>
        </div>
      </div>
    </div>
  );
}

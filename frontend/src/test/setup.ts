import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// globals:false olduğu için Testing Library'nin otomatik cleanup'ı devreye girmiyor —
// her testten sonra render edilen DOM'u elle temizliyoruz, yoksa testler arası
// önceki render'lar DOM'da birikip getByTestId/getByText gibi sorguları bozar.
afterEach(() => {
  cleanup()
})

// jsdom ResizeObserver'ı desteklemiyor ve layout hesaplamaz (getBoundingClientRect hep 0
// döner) — recharts'ın ResponsiveContainer'ı ve grafik widget'larının elle kurduğu
// ResizeObserver'lar bu yüzden hiç tetiklenmez. observe() çağrıldığı anda callback'i
// sabit, sıfırdan büyük bir boyutla senkron tetikleyerek resize mantığını test edilebilir kılıyoruz.
export class ResizeObserverMock {
  // Testlerin, kütüphanenin kurduğu ResizeObserver'ı elle (özel entries ile) tetikleyebilmesi
  // için son oluşturulan örneği burada tutuyoruz (ör. PortfolioChartWidget'ın kendi guard
  // mantığını — alakasız hedef/boş entries — test edebilmek için).
  static lastInstance: ResizeObserverMock | undefined
  callback: ResizeObserverCallback
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    ResizeObserverMock.lastInstance = this
  }
  observe(target: Element) {
    this.callback(
      [{ target, contentRect: { width: 400, height: 300 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver
    )
  }
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver

Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 400 })
Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 300 })

// jsdom Element.prototype.scrollIntoView'i uygulamıyor — sohbet ekranlarındaki
// otomatik aşağı kaydırma efektleri bunu çağırınca patlamasın diye no-op veriyoruz.
Element.prototype.scrollIntoView = () => {}

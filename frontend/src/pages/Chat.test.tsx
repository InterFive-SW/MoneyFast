import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Chat from './Chat'
import { ChatProvider } from '../context/ChatContext'
import { api } from '../api/client'

function renderPage() {
  return render(
    <ChatProvider>
      <Chat />
    </ChatProvider>
  )
}

function sendMessage(text: string) {
  const textarea = screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...')
  fireEvent.change(textarea, { target: { value: text } })
  fireEvent.click(screen.getByLabelText('Gönder'))
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Chat', () => {
  it('mesaj yokken boş durumu, önerilen soruları ve "Henüz sohbet bulunmuyor" gösterir', () => {
    renderPage()
    expect(screen.getByText('Nasıl yardımcı olabilirim?')).toBeInTheDocument()
    expect(screen.getByText('Henüz sohbet bulunmuyor.')).toBeInTheDocument()
  })

  it('önerilen bir soruya tıklanınca mesaj gönderilir ve sohbet listesine eklenir', async () => {
    vi.spyOn(api, 'post').mockReturnValue(new Promise(() => {})) // yazıyor durumunu görmek için askıda bırak
    renderPage()
    fireEvent.click(screen.getByText("BIST 100'de bugün en çok kazandıranlar"))

    await waitFor(() => expect(screen.getByText("BIST 100'de bugün en çok kazandıranlar")).toBeInTheDocument())
    expect(document.querySelector('.animate-bounce')).not.toBeNull() // TypingIndicator
    expect(screen.queryByText('Henüz sohbet bulunmuyor.')).not.toBeInTheDocument()
  })

  it('yeni sohbet butonuna basınca ikinci bir oturum oluşturulur ve arasında geçiş yapılabilir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'Merhaba, size nasıl yardımcı olabilirim?', id: 'ai-1' })
    renderPage()

    sendMessage('İlk sohbetim')
    await waitFor(() => expect(screen.getByText('Merhaba, size nasıl yardımcı olabilirim?')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Yeni Sohbet'))
    expect(screen.getByText('Nasıl yardımcı olabilirim?')).toBeInTheDocument() // yeni oturum boş

    // Eski oturuma geri dön
    fireEvent.click(screen.getByText('İlk sohbetim'))
    await waitFor(() => expect(screen.getByText('Merhaba, size nasıl yardımcı olabilirim?')).toBeInTheDocument())
  })

  it('bir sohbeti silme butonu satır tıklamasını tetiklemeden oturumu kaldırır', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'yanıt', id: 'ai-1' })
    renderPage()

    sendMessage('Silinecek sohbet')
    await waitFor(() => expect(screen.getAllByText('Silinecek sohbet').length).toBeGreaterThan(0))

    fireEvent.click(screen.getByTitle('Sohbeti Sil'))
    expect(screen.getByText('Henüz sohbet bulunmuyor.')).toBeInTheDocument()
  })

  it('backend context_topic dönerse mesaj varken bağlam paneli gerçek içerikle render edilir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'THYAO analiz ediliyor', id: 'ai-1', context_topic: 'THYAO' })
    renderPage()

    sendMessage('THYAO hakkında bilgi ver')
    await waitFor(() => expect(screen.getByText('Anlık Fiyat')).toBeInTheDocument())
    expect(screen.queryByText('Akıllı Bağlam Paneli')).not.toBeInTheDocument()
  })
})

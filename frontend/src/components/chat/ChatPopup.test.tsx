import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPopup from './ChatPopup'
import { ChatProvider } from '../../context/ChatContext'
import { api } from '../../api/client'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

function renderPopup(isOpen: boolean, onClose = vi.fn()) {
  return render(
    <MemoryRouter>
      <ChatProvider>
        <ChatPopup isOpen={isOpen} onClose={onClose} />
      </ChatProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  localStorage.clear()
  navigateMock.mockClear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ChatPopup', () => {
  it('kapalıyken hiçbir şey render etmez', () => {
    const { container } = renderPopup(false)
    expect(container).toBeEmptyDOMElement()
  })

  it('açıkken ve mesaj yokken boş durum mesajını gösterir', () => {
    renderPopup(true)
    expect(screen.getByText('Sohbete başlamak için bir mesaj yazın...')).toBeInTheDocument()
  })

  it('kapatma butonuna basınca onClose çağrılır', () => {
    const onClose = vi.fn()
    renderPopup(true, onClose)
    fireEvent.click(screen.getByTitle('Kapat'))
    expect(onClose).toHaveBeenCalled()
  })

  it('tam ekran butonuna basınca onClose çağrılır ve /chat\'e yönlendirir', () => {
    const onClose = vi.fn()
    renderPopup(true, onClose)
    fireEvent.click(screen.getByTitle('Sohbet Sayfasına Git'))
    expect(onClose).toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/chat')
  })

  it('mesaj gönderilince kullanıcı mesajını ve yazıyor göstergesini render eder', async () => {
    vi.spyOn(api, 'post').mockReturnValue(new Promise(() => {}))
    renderPopup(true)

    const textarea = screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...')
    fireEvent.change(textarea, { target: { value: 'Merhaba' } })
    fireEvent.click(screen.getByLabelText('Gönder'))

    await waitFor(() => expect(screen.getByText('Merhaba')).toBeInTheDocument())
    expect(document.querySelector('.animate-bounce')).not.toBeNull()
  })

  it('yanıt geldiğinde AI mesajını gösterir', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({ text: 'Size nasıl yardımcı olabilirim?', id: 'ai-1' })
    renderPopup(true)

    fireEvent.change(screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...'), { target: { value: 'Merhaba' } })
    fireEvent.click(screen.getByLabelText('Gönder'))

    await waitFor(() => expect(screen.getByText('Size nasıl yardımcı olabilirim?')).toBeInTheDocument())
  })

  it('açıldığında gecikmeli scrollToBottom tetiklenir', async () => {
    vi.useFakeTimers()
    renderPopup(true)
    await vi.advanceTimersByTimeAsync(150)
    vi.useRealTimers()
  })
})

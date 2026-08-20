import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ChatInput from './ChatInput'

describe('ChatInput', () => {
  it('boşken gönder butonu devre dışıdır, mesaj yazınca etkinleşir', () => {
    render(<ChatInput onSendMessage={vi.fn()} />)
    const sendBtn = screen.getByLabelText('Gönder') as HTMLButtonElement
    expect(sendBtn.disabled).toBe(true)

    fireEvent.change(screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...'), {
      target: { value: 'Merhaba' },
    })
    expect(sendBtn.disabled).toBe(false)
  })

  it('yalnızca boşluk girilirse gönder butonu devre dışı kalır', () => {
    render(<ChatInput onSendMessage={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...'), {
      target: { value: '   ' },
    })
    expect((screen.getByLabelText('Gönder') as HTMLButtonElement).disabled).toBe(true)
  })

  it('gönder butonuna basınca metni kırpıp iletir ve kutuyu temizler', () => {
    const onSendMessage = vi.fn()
    render(<ChatInput onSendMessage={onSendMessage} />)
    const textarea = screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '  Merhaba  ' } })
    fireEvent.click(screen.getByLabelText('Gönder'))
    expect(onSendMessage).toHaveBeenCalledWith('Merhaba')
    expect(textarea.value).toBe('')
  })

  it('Enter tuşuna basınca mesaj gönderilir', () => {
    const onSendMessage = vi.fn()
    render(<ChatInput onSendMessage={onSendMessage} />)
    const textarea = screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...')
    fireEvent.change(textarea, { target: { value: 'Merhaba' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(onSendMessage).toHaveBeenCalledWith('Merhaba')
  })

  it('Shift+Enter yeni satır ekler, mesaj göndermez', () => {
    const onSendMessage = vi.fn()
    render(<ChatInput onSendMessage={onSendMessage} />)
    const textarea = screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...')
    fireEvent.change(textarea, { target: { value: 'Merhaba' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(onSendMessage).not.toHaveBeenCalled()
  })

  it('disabled iken metin girilse dahi gönder butonu devre dışı kalır ve Enter göndermez', () => {
    const onSendMessage = vi.fn()
    render(<ChatInput onSendMessage={onSendMessage} disabled />)
    const textarea = screen.getByPlaceholderText('Yapay zeka asistanına sorunuzu yazın...')
    expect(textarea).toBeDisabled()
    expect((screen.getByLabelText('Gönder') as HTMLButtonElement).disabled).toBe(true)

    // disabled=true iken handleSend'in kendi koruması da mesajı engellemeli
    // (buton zaten disabled olsa da).
    fireEvent.change(textarea, { target: { value: 'Merhaba' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(onSendMessage).not.toHaveBeenCalled()
  })
})

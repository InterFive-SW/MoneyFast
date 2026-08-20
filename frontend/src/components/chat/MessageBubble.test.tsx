import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MessageBubble from './MessageBubble'
import type { ChatMessage } from '../../types/chat'

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'm1',
    text: 'Merhaba',
    sender: 'ai',
    timestamp: new Date('2026-08-20T10:30:00'),
    ...overrides,
  }
}

describe('MessageBubble', () => {
  it('kullanıcı mesajında avatar göstermez, AI stilini kullanmaz', () => {
    render(<MessageBubble message={makeMessage({ sender: 'user', text: 'Selam' })} />)
    expect(screen.getByText('Selam')).toBeInTheDocument()
    expect(screen.queryByText('MF')).not.toBeInTheDocument()
  })

  it('AI mesajında avatar gösterir', () => {
    render(<MessageBubble message={makeMessage({ sender: 'ai', text: 'Merhaba, size nasıl yardımcı olabilirim?' })} />)
    expect(screen.getByText('MF')).toBeInTheDocument()
  })

  it('chart widget\'lı mesajı render eder', () => {
    render(
      <MessageBubble
        message={makeMessage({
          widget: { type: 'chart', payload: { title: 'THYAO', data: [{ name: 'Oca', value: 100 }] } },
        })}
      />
    )
    expect(screen.getByText('THYAO')).toBeInTheDocument()
  })

  it('action widget\'lı mesajı render eder', () => {
    render(
      <MessageBubble
        message={makeMessage({
          widget: {
            type: 'action',
            payload: { message: 'İşlemi onaylıyor musunuz?', confirmLabel: 'Onayla', cancelLabel: 'İptal', actionId: 'a1', asset: 'THYAO', amount: 10, action: 'buy' },
          },
        })}
      />
    )
    expect(screen.getByText('İşlemi onaylıyor musunuz?')).toBeInTheDocument()
  })

  it('portfolio widget\'lı mesajı render eder', () => {
    render(
      <MessageBubble
        message={makeMessage({
          widget: { type: 'portfolio', payload: { total_value: 1000, total_profit_loss: 50, positions: [] } },
        })}
      />
    )
    expect(screen.getByText('Mevcut Portföy Durumu')).toBeInTheDocument()
  })
})

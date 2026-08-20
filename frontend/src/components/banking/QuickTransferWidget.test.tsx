import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import QuickTransferWidget from './QuickTransferWidget'
import type { SavedContact } from '../../data/mockBankingData'

const contacts: SavedContact[] = [
  { id: 'c-1', name: 'Mustafa', iban: 'TR11...', avatarInitials: 'M', avatarColor: 'bg-emerald-500' },
  { id: 'c-2', name: 'Şevval', iban: 'TR22...', avatarInitials: 'Ş', avatarColor: 'bg-purple-500' },
]

describe('QuickTransferWidget', () => {
  it('kişi seçilmeden önce uyarı mesajını gösterir ve Gönder disabled olur', () => {
    render(<QuickTransferWidget contacts={contacts} />)
    expect(screen.getByText('Lütfen transfer yapmak için bir kişi seçin.')).toBeInTheDocument()
    expect(screen.getByText('Gönder')).toBeDisabled()
  })

  it('bir kişi seçilince uyarı kalkar, tutar girilince Gönder aktif olur', () => {
    render(<QuickTransferWidget contacts={contacts} />)
    fireEvent.click(screen.getByText('Mustafa'))
    expect(screen.queryByText('Lütfen transfer yapmak için bir kişi seçin.')).not.toBeInTheDocument()
    expect(screen.getByText('Gönder')).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: '100' } })
    expect(screen.getByText('Gönder')).toBeEnabled()
  })

  it('"Yeni Kişi" seçilebilir', () => {
    render(<QuickTransferWidget contacts={contacts} />)
    fireEvent.click(screen.getByText('Yeni Kişi'))
    expect(screen.queryByText('Lütfen transfer yapmak için bir kişi seçin.')).not.toBeInTheDocument()
  })
})

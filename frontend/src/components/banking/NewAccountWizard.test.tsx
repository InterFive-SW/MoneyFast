import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NewAccountWizard from './NewAccountWizard'
import type { BankingContextType } from '../../pages/Banking'

const navigateMock = vi.fn()
const handleAccountCreate = vi.fn()

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useOutletContext: () => ({ handleAccountCreate } as Partial<BankingContextType>),
  }
})

beforeEach(() => {
  navigateMock.mockClear()
  handleAccountCreate.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

const ibanRegex = /^TR\d{2} 0006 2001 0450 0006 6677 \d{2}$/

describe('NewAccountWizard', () => {
  it('1. adımda Menüye Dön tıklanınca /banking\'e yönlendirir', () => {
    render(<NewAccountWizard />)
    fireEvent.click(screen.getByText('Menüye Dön'))
    expect(navigateMock).toHaveBeenCalledWith('/banking')
  })

  it('2. adımda Geri tıklanınca 1. adıma döner', () => {
    render(<NewAccountWizard />)
    fireEvent.click(screen.getByText('Devam Et'))
    expect(screen.getByText('Para Birimi Seçimi')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Geri'))
    expect(screen.getByText('Hesap Türünü Seçin')).toBeInTheDocument()
    expect(screen.getByText('Menüye Dön')).toBeInTheDocument()
  })

  it('varsayılan seçimlerle ve boş isimle devam edilince otomatik isim üretilir', () => {
    render(<NewAccountWizard />)
    fireEvent.click(screen.getByText('Vadesiz Hesap'))
    fireEvent.click(screen.getByText('Devam Et')) // step1 -> 2
    fireEvent.click(screen.getByText('Devam Et')) // step2 -> 3
    fireEvent.click(screen.getByText('Devam Et')) // step3 -> 4

    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('Hesabı Oluştur'))

    expect(handleAccountCreate).toHaveBeenCalledWith('TRY', 'checking', 'TRY Vadesiz Hesap', expect.stringMatching(ibanRegex))
    expect(screen.getByText('Tebrikler!')).toBeInTheDocument()
    expect(screen.getByText(/Vadesiz TRY hesabınız/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Hesaplarıma Git'))
    expect(navigateMock).toHaveBeenCalledWith('/banking/accounts')
  })

  it('vadeli hesap, EUR para birimi ve özel isimle oluşturma isteği kendi verileriyle gönderilir', () => {
    render(<NewAccountWizard />)
    fireEvent.click(screen.getByText('Vadeli Hesap'))
    fireEvent.click(screen.getByText('Devam Et'))

    fireEvent.click(screen.getByText('EUR'))
    fireEvent.click(screen.getByText('Devam Et'))

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Tatil Hesabım' } })
    fireEvent.click(screen.getByText('Devam Et'))

    expect(screen.getByText('Vadeli Hesap')).toBeInTheDocument()
    expect(screen.getByText('Tatil Hesabım')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('Hesabı Oluştur'))

    expect(handleAccountCreate).toHaveBeenCalledWith('EUR', 'savings', 'Tatil Hesabım', expect.stringMatching(ibanRegex))
    expect(screen.getByText(/Vadeli EUR hesabınız/)).toBeInTheDocument()
  })

  it('vadeli hesap, boş isimle devam edilince Vadeli otomatik isim üretilir', () => {
    render(<NewAccountWizard />)
    fireEvent.click(screen.getByText('Vadeli Hesap'))
    fireEvent.click(screen.getByText('Devam Et'))
    fireEvent.click(screen.getByText('Devam Et'))
    fireEvent.click(screen.getByText('Devam Et'))

    expect(screen.getByText('TRY Vadeli Hesap')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('Hesabı Oluştur'))
    expect(handleAccountCreate).toHaveBeenCalledWith('TRY', 'savings', 'TRY Vadeli Hesap', expect.stringMatching(ibanRegex))
  })

  it('onay kutusu işaretlenmeden Hesabı Oluştur devre dışı kalır ve tıklamak bir şey tetiklemez', () => {
    render(<NewAccountWizard />)
    fireEvent.click(screen.getByText('Devam Et'))
    fireEvent.click(screen.getByText('Devam Et'))
    fireEvent.click(screen.getByText('Devam Et'))

    const submitButton = screen.getByText('Hesabı Oluştur')
    expect(submitButton).toBeDisabled()
    fireEvent.click(submitButton)
    expect(handleAccountCreate).not.toHaveBeenCalled()
    expect(screen.getByText('Sözleşme ve Onay')).toBeInTheDocument()
  })
})

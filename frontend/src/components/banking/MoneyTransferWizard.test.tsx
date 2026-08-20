import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MoneyTransferWizard from './MoneyTransferWizard'
import type { BankAccount } from '../../data/mockBankingData'
import type { BankingContextType } from '../../pages/Banking'

const navigateMock = vi.fn()
const handleTransfer = vi.fn()
let mockAccounts: BankAccount[]

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
    useOutletContext: () => ({
      data: { accounts: mockAccounts },
      handleTransfer,
    } as Partial<BankingContextType>),
  }
})

const checking: BankAccount = { id: 'acc-1', name: 'Vadesiz Maaş Hesabı', type: 'checking', balance: 12500.5, currency: 'TRY', accountNumber: 'TR120006200000012345' }
const savings: BankAccount = { id: 'acc-2', name: 'Birikim Hesabı', type: 'savings', balance: 130000, currency: 'TRY', accountNumber: 'TR120006200009876543' }

function renderWizard(state?: Record<string, unknown>) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/banking/transfer', state }]}>
      <MoneyTransferWizard />
    </MemoryRouter>
  )
}

beforeEach(() => {
  navigateMock.mockClear()
  handleTransfer.mockClear()
  mockAccounts = [checking, savings]
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('MoneyTransferWizard', () => {
  it('1. adımda geri butonu /banking\'e yönlendirir', () => {
    renderWizard()
    fireEvent.click(screen.getAllByRole('button')[0])
    expect(navigateMock).toHaveBeenCalledWith('/banking')
  })

  it('2. adımda geri butonu bir önceki adıma döner', () => {
    renderWizard()
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    fireEvent.click(screen.getByText('DEVAM'))
    expect(screen.getByText('Gönderen Hesap Seçimi')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button')[0])
    expect(screen.getByText('Kayıtlı Alıcılar')).toBeInTheDocument()
  })

  it('hesap yokken gönderen hesap otomatik seçilmez', () => {
    mockAccounts = []
    renderWizard()
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    fireEvent.click(screen.getByText('DEVAM'))
    expect(screen.getByText('DEVAM')).toBeDisabled()
  })

  it('kayıtlı alıcı seçilmeden DEVAM devre dışı kalır, seçilince aktif olur', () => {
    renderWizard()
    expect(screen.getByText('DEVAM')).toBeDisabled()
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    expect(screen.getByText('DEVAM')).toBeEnabled()
    expect(screen.getAllByText('SIK KULLANILAN').length).toBeGreaterThan(0)
  })

  it('kayıtlı alıcı ile tam akış: gönderen hesap, tutar, onay ve başarı ekranı', () => {
    renderWizard()
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    fireEvent.click(screen.getByText('DEVAM'))

    expect(screen.getByText('Gönderen Hesap Seçimi')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Birikim Hesabı'))
    fireEvent.click(screen.getByText('DEVAM'))

    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: '500' } })
    fireEvent.click(screen.getByText('DEVAM'))

    expect(screen.getByText('Ahmet Yılmaz')).toBeInTheDocument()
    expect(screen.getAllByText('Birikim Hesabı').length).toBeGreaterThan(0)
    fireEvent.change(screen.getByPlaceholderText('Açıklama girebilirsiniz (İsteğe bağlı)'), { target: { value: 'Kira' } })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Kira Ödemesi' } })

    fireEvent.click(screen.getByText('ONAYLA'))
    expect(handleTransfer).toHaveBeenCalledWith(500, 'acc-2', 'TR', 'Kira')
    expect(screen.getByText('İşleminiz Başarıyla Alınmıştır')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Ana Menüye Dön'))
    expect(navigateMock).toHaveBeenCalledWith('/banking')
  })

  it('yeni alıcı (IBAN) akışı: kayıtlı alıcı olarak ekle açılıp kapanabilir, handleTransfer alıcı adıyla çağrılır', () => {
    renderWizard()
    fireEvent.click(screen.getByText('Yeni Bir Alıcı'))
    expect(screen.getByText('DEVAM')).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('TR...'), { target: { value: 'TR720006200104500066770X' } })
    fireEvent.change(screen.getByPlaceholderText('Alıcı Adı Soyadı'), { target: { value: 'Elif Kaya' } })
    expect(screen.getByText('DEVAM')).toBeEnabled()

    fireEvent.click(screen.getByText('Kayıtlı alıcı olarak ekle').nextElementSibling!)
    fireEvent.click(screen.getByText('DEVAM'))
    fireEvent.click(screen.getByText('Vadesiz Maaş Hesabı'))
    fireEvent.click(screen.getByText('DEVAM'))
    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: '250' } })
    fireEvent.click(screen.getByText('DEVAM'))

    expect(screen.getByText('Elif Kaya')).toBeInTheDocument()
    fireEvent.click(screen.getByText('ONAYLA'))
    expect(handleTransfer).toHaveBeenCalledWith(250, 'acc-1', 'Elif Kaya', '')
  })

  it('Hesap No İle ve Kolay Adres İle sekmeleri IBAN formunu gizler, IBAN İle sekmesine dönülebilir', () => {
    renderWizard()
    fireEvent.click(screen.getByText('Yeni Bir Alıcı'))
    fireEvent.click(screen.getByText('Hesap No İle'))
    expect(screen.queryByPlaceholderText('TR...')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Kolay Adres İle'))
    expect(screen.queryByPlaceholderText('TR...')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('IBAN İle'))
    expect(screen.getByPlaceholderText('TR...')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Kayıtlı Alıcılar'))
    expect(screen.getByText('Ahmet Yılmaz')).toBeInTheDocument()
  })

  it('tutar bakiyeyi aşarsa veya boşsa DEVAM devre dışı kalır', () => {
    renderWizard()
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    fireEvent.click(screen.getByText('DEVAM'))
    fireEvent.click(screen.getByText('Vadesiz Maaş Hesabı'))
    fireEvent.click(screen.getByText('DEVAM'))

    expect(screen.getByText('DEVAM')).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: '999999' } })
    expect(screen.getByText('DEVAM')).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: '100' } })
    expect(screen.getByText('DEVAM')).toBeEnabled()
  })

  it('location.state.fromAccountId gönderen hesabı önceden seçer', () => {
    renderWizard({ fromAccountId: 'acc-2' })
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    fireEvent.click(screen.getByText('DEVAM'))
    fireEvent.click(screen.getByText('DEVAM')) // step2 zaten acc-2 seçili, direkt devam
    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: '100' } })
    fireEvent.click(screen.getByText('DEVAM'))
    expect(screen.getAllByText('Birikim Hesabı').length).toBeGreaterThan(0)
  })

  function advanceToStep4() {
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    fireEvent.click(screen.getByText('DEVAM'))
    fireEvent.click(screen.getByText('DEVAM'))
    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: '100' } })
    fireEvent.click(screen.getByText('DEVAM'))
  }

  it('4. adımdaki kalem düzenleme ikonları ilgili adıma geri döner', () => {
    renderWizard()
    advanceToStep4()

    fireEvent.click(screen.getByText('Alıcı Hesap').nextElementSibling!.nextElementSibling!.nextElementSibling!.nextElementSibling!)
    expect(screen.getByText('Kayıtlı Alıcılar')).toBeInTheDocument()

    advanceToStep4()
    fireEvent.click(screen.getByText('Gönderen Hesap').nextElementSibling!.nextElementSibling!.nextElementSibling!.nextElementSibling!)
    expect(screen.getByText('Gönderen Hesap Seçimi')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Vadesiz Maaş Hesabı'))
    fireEvent.click(screen.getByText('DEVAM'))
    fireEvent.change(screen.getByPlaceholderText('0,00'), { target: { value: '100' } })
    fireEvent.click(screen.getByText('DEVAM'))

    fireEvent.click(screen.getByText('Tutar').nextElementSibling!.nextElementSibling!)
    expect(screen.getByPlaceholderText('0,00')).toBeInTheDocument()
  })

  it('stepper üzerinden tamamlanmış bir adıma dönülebilir, ileri adıma tıklamak etkisiz kalır', () => {
    renderWizard()
    fireEvent.click(screen.getByText('Ahmet Yılmaz'))
    fireEvent.click(screen.getByText('DEVAM'))

    fireEvent.click(screen.getByText('ALICI HESAP'))
    expect(screen.getByText('Kayıtlı Alıcılar')).toBeInTheDocument()

    fireEvent.click(screen.getByText('TUTAR BELİRLEME'))
    expect(screen.getByText('Kayıtlı Alıcılar')).toBeInTheDocument()
  })
})

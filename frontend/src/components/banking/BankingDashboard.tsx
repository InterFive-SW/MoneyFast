import React from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { BankingContextType } from '../../pages/Banking'
import AccountHeroWidget from './AccountHeroWidget'
import BankingMenu from './BankingMenu'

/**
 * BankingDashboard Bileşeni
 * 
 * Ana bankacılık ekranıdır. En üstte AccountHeroWidget (özet/hızlı işlemler),
 * altında ise BankingMenu (tüm işlemler) listelenir.
 */
export default function BankingDashboard() {
  const navigate = useNavigate()
  const { data, openFeatureNotReadyModal, openBillPaymentModal } = useOutletContext<BankingContextType>()

  return (
    <div className="w-full animate-fade-in">
      <AccountHeroWidget 
        accounts={data.accounts}
        totalAssets={data.totalAssets}
        onNavigateToAccounts={() => navigate('/banking/accounts')}
        onOpenTransfer={() => navigate('/banking/transfer')}
        onOpenBillPayment={openBillPaymentModal}
        onFeatureNotReady={openFeatureNotReadyModal}
      />
      
      <BankingMenu 
        onNavigateToAccounts={() => navigate('/banking/accounts')}
        onOpenTransfer={() => navigate('/banking/transfer')}
        onOpenBillPayment={openBillPaymentModal}
        onFeatureNotReady={openFeatureNotReadyModal}
      />
    </div>
  )
}

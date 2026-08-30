/**
 * App — Uygulama Kök Bileşeni (v2)
 *
 * Değişiklikler:
 *  - `UserProvider` tüm rota ağacını sarıyor
 *  - `ProtectedRoute` korumalı rotaları guard altına alıyor
 *  - Auth / public rotalar değişmedi
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { UserProvider }     from './contexts/UserContext'
import ProtectedRoute       from './components/auth/ProtectedRoute'
import DashboardLayout      from './components/layout/DashboardLayout'
import Landing              from './pages/Landing'
import Home                 from './pages/Home'
import Login                from './pages/Login'
import SavedPayeesView     from './components/banking/SavedPayeesView'
import AdminRoute          from './components/admin/AdminRoute'
import AdminLayout         from './components/admin/AdminLayout'
import AdminLogin          from './pages/admin/AdminLogin'
import AdminUsers          from './pages/admin/AdminUsers'
import AdminBills          from './pages/admin/AdminBills'
import ForgotPassword       from './pages/ForgotPassword'
import ResetPassword        from './pages/ResetPassword'
import VerifyEmail          from './pages/VerifyEmail'
import Register             from './pages/Register'
import RegisterPassword     from './pages/RegisterPassword'
import Dashboard            from './pages/Dashboard'
import Chat                 from './pages/Chat'
import Portfolio            from './pages/Portfolio'
import Banking              from './pages/Banking'
import BankingDashboard     from './components/banking/BankingDashboard'
import AccountsView         from './components/banking/AccountsView'
import AccountTransactionsView from './components/banking/AccountTransactionsView'
import MoneyTransferWizard  from './components/banking/MoneyTransferWizard'
// NewAccountWizard bilerek route'suz duruyor — backend'de hesap açma ucu
// olmadığı için sihirbaz hesabı yalnızca ekranda yaratıyordu. Uç eklendiğinde
// import ve route birlikte geri gelir; bkz. AccountsView'daki açıklama.
import CardsView            from './components/banking/CardsView'
import NewCardWizard        from './components/banking/NewCardWizard'
import Investment           from './pages/Investment'
import StocksScreen         from './pages/markets/StocksScreen'
import StockDetail          from './pages/markets/StockDetail'
import FundsScreen          from './pages/markets/FundsScreen'
import FundDetail           from './pages/markets/FundDetail'
import IndicesScreen        from './pages/markets/IndicesScreen'
import SectorsScreen        from './pages/markets/SectorsScreen'
import AnalysesScreen       from './pages/markets/AnalysesScreen'
import Analiz from './pages/Analiz'
import GenelBakis from './pages/analiz/GenelBakis'
import RiskSekmesi from './pages/analiz/RiskSekmesi'
import Senaryo from './pages/analiz/Senaryo'
import Settings from './pages/Settings'

export default function App() {
  return (
    /*
     * UserProvider kapsayıcısı BrowserRouter'ın içine alınır çünkü
     * UserContext içindeki useNavigate / useLocation çağrıları Router
     * bağlamını gerektirir.
     */
    <BrowserRouter>
      <UserProvider>
        <Routes>
          {/* ── Genel / Auth Rotaları ──────────────────────────────────── */}
          <Route path="/"                 element={<Landing />}          />
          <Route path="login"             element={<Login />}            />
          {/* Operator area. Outside ProtectedRoute and DashboardLayout on
              purpose: an administrator holds no customer session and none
              of the customer navigation. */}
          <Route path="admin/login"       element={<AdminLogin />}       />
          <Route path="admin" element={<AdminRoute />}>
            <Route element={<AdminLayout />}>
              <Route index element={<Navigate to="/admin/users" replace />} />
              <Route path="users" element={<AdminUsers />} />
              <Route path="bills" element={<AdminBills />} />
            </Route>
          </Route>
          <Route path="forgot-password"   element={<ForgotPassword />}   />
          <Route path="reset-password"    element={<ResetPassword />}    />
          <Route path="verify-email"      element={<VerifyEmail />}      />
          <Route path="register"          element={<Register />}         />
          <Route path="register/password" element={<RegisterPassword />} />

          {/* ── Korumalı Rotalar ───────────────────────────────────────── */}
          {/*
            Önce ProtectedRoute JWT kontrolü yapar.
            Geçerliyse DashboardLayout (Sidebar + Header) render edilir.
            Geçersizse /login'e yönlendirilir (replace=true ile).
          */}
          <Route element={<ProtectedRoute />}>
            <Route element={<DashboardLayout />}>
              {/* Ana sayfa bakiyelerle açılır, tıpkı bir bankacılık
                  uygulaması gibi. Uygulamayı ayıran yatırım sohbeti bir tık
                  uzakta; ilk görülen şey olarak değil. */}
              <Route path="dashboard"     element={<Home />}       />
              <Route path="hizli-finans"  element={<Dashboard />}  />
              <Route path="chat"       element={<Chat />}       />
              <Route path="portfolio"  element={<Portfolio />}  />
              <Route path="banking" element={<Banking />}>
                <Route index element={<BankingDashboard />} />
                <Route path="accounts" element={<AccountsView />} />
                <Route path="accounts/:accountId/transactions" element={<AccountTransactionsView />} />
                <Route path="cards" element={<CardsView />} />
                <Route path="saved" element={<SavedPayeesView />} />
                <Route path="transfer" element={<MoneyTransferWizard />} />
                <Route path="new-card" element={<NewCardWizard />} />
              </Route>
              <Route path="analiz" element={<Analiz />}>
                <Route index             element={<Navigate to="genel" replace />} />
                <Route path="genel"      element={<GenelBakis />} />
                <Route path="risk"       element={<RiskSekmesi />} />
                <Route path="senaryo"    element={<Senaryo />} />
              </Route>
              {/* Portföy Analizi ve Risk Analizi tek çatı altında
                  birleşti. Eski adresler yer imlerinde ve paylaşılan
                  bağlantılarda duruyor, o yüzden 404 değil yönlendirme. */}
              <Route path="analytics"  element={<Navigate to="/analiz/genel" replace />} />
              <Route path="investment" element={<Investment />}>
                <Route index                element={<Navigate to="hisseler" replace />} />
                <Route path="hisseler"       element={<StocksScreen />}  />
                <Route path="hisseler/:symbol" element={<StockDetail />} />
                <Route path="fonlar"         element={<FundsScreen />}   />
                <Route path="fonlar/:code"   element={<FundDetail />}    />
                <Route path="endeksler"      element={<IndicesScreen />} />
                <Route path="sektorler"      element={<SectorsScreen />} />
                <Route path="analizler"      element={<AnalysesScreen />} />
              </Route>
              <Route path="risk"       element={<Navigate to="/analiz/risk" replace />} />
              <Route path="settings"   element={<Settings />}   />
            </Route>
          </Route>
        </Routes>
      </UserProvider>
    </BrowserRouter>
  )
}

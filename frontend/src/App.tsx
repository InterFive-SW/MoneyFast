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
import Login                from './pages/Login'
import ForgotPassword       from './pages/ForgotPassword'
import Register             from './pages/Register'
import RegisterPassword     from './pages/RegisterPassword'
import Dashboard            from './pages/Dashboard'
import Chat                 from './pages/Chat'
import Portfolio            from './pages/Portfolio'
import Banking              from './pages/Banking'
import Investment           from './pages/Investment'
import Risk                 from './pages/Risk'
import StocksScreen         from './pages/markets/StocksScreen'
import StockDetail          from './pages/markets/StockDetail'
import FundsScreen          from './pages/markets/FundsScreen'
import FundDetail           from './pages/markets/FundDetail'
import IndicesScreen        from './pages/markets/IndicesScreen'
import SectorsScreen        from './pages/markets/SectorsScreen'
import AnalysesScreen       from './pages/markets/AnalysesScreen'

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
          <Route path="forgot-password"   element={<ForgotPassword />}   />
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
              <Route path="dashboard"  element={<Dashboard />}  />
              <Route path="chat"       element={<Chat />}       />
              <Route path="portfolio"  element={<Portfolio />}  />
              <Route path="banking"    element={<Banking />}    />
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
              <Route path="risk"       element={<Risk />}       />
            </Route>
          </Route>
        </Routes>
      </UserProvider>
    </BrowserRouter>
  )
}

import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Portfolio from './pages/Portfolio'
import Banking from './pages/Banking'
import Investment from './pages/Investment'
import Risk from './pages/Risk'
import Login from './pages/Login'
import ForgotPassword from './pages/ForgotPassword'
import Register from './pages/Register'
import RegisterPassword from './pages/RegisterPassword'

function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-100">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="login" element={<Login />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        <Route path="register" element={<Register />} />
        <Route path="register/password" element={<RegisterPassword />} />
        
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="chat" element={<Chat />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="banking" element={<Banking />} />
          <Route path="investment" element={<Investment />} />
          <Route path="risk" element={<Risk />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

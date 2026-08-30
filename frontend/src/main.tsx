import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// --- GLOBAL ERROR OVERLAY FOR DEBUGGING ---
window.onerror = function(message, source, lineno, colno, error) {
  const errorDiv = document.createElement('div')
  errorDiv.style.position = 'fixed'
  errorDiv.style.top = '0'
  errorDiv.style.left = '0'
  errorDiv.style.width = '100vw'
  errorDiv.style.height = '100vh'
  errorDiv.style.backgroundColor = 'red'
  errorDiv.style.color = 'white'
  errorDiv.style.zIndex = '999999'
  errorDiv.style.padding = '2rem'
  errorDiv.style.fontSize = '24px'
  errorDiv.style.fontFamily = 'monospace'
  errorDiv.style.overflow = 'auto'
  errorDiv.innerHTML = `
    <h1>CRITICAL CRASH! LÜTFEN BUNU KOPYALAYIN:</h1>
    <hr/>
    <p>Message: ${message}</p>
    <p>Source: ${source}:${lineno}:${colno}</p>
    <pre>${error?.stack || 'No stack trace'}</pre>
  `
  document.body.appendChild(errorDiv)
}
window.addEventListener('unhandledrejection', function(event) {
  const errorDiv = document.createElement('div')
  errorDiv.style.position = 'fixed'
  errorDiv.style.top = '0'
  errorDiv.style.left = '0'
  errorDiv.style.width = '100vw'
  errorDiv.style.height = '100vh'
  errorDiv.style.backgroundColor = 'purple'
  errorDiv.style.color = 'white'
  errorDiv.style.zIndex = '999999'
  errorDiv.style.padding = '2rem'
  errorDiv.style.fontSize = '24px'
  errorDiv.style.fontFamily = 'monospace'
  errorDiv.style.overflow = 'auto'
  errorDiv.innerHTML = `
    <h1>UNHANDLED PROMISE REJECTION! KOPYALAYIN:</h1>
    <hr/>
    <pre>${event.reason?.stack || event.reason}</pre>
  `
  document.body.appendChild(errorDiv)
})
// -------------------------------------------

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

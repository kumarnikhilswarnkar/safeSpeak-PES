import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App.jsx'
import { AuthProvider } from './auth/AuthContext.jsx'
import { AssistantProvider } from './components/assistant/AssistantContext.jsx'
import { ToastProvider } from './components/Toast.jsx'
import './styles/app.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AssistantProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </AssistantProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)

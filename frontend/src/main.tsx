import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { aiDevtoolsPlugin } from '@tanstack/react-ai-devtools'
import { TanStackDevtools } from '@tanstack/react-devtools'
import './index.css'
import App from './App.tsx'

const appRoot = document.getElementById('root')

if (!appRoot) {
  throw new Error('Root element not found')
}

createRoot(appRoot).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

if (import.meta.env.DEV) {
  const devtoolsRootId = 'devtools-root'
  const connectToServerBus = import.meta.env.VITE_DEVTOOLS_SERVER_BUS === 'true'
  let devtoolsRoot = document.getElementById(devtoolsRootId)

  if (!devtoolsRoot) {
    devtoolsRoot = document.createElement('div')
    devtoolsRoot.id = devtoolsRootId
    document.body.appendChild(devtoolsRoot)
  }

  createRoot(devtoolsRoot).render(
    <TanStackDevtools
      plugins={[aiDevtoolsPlugin()]}
      eventBusConfig={{ connectToServerBus }}
    />,
  )
}

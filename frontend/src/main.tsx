import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { Gallery } from './Gallery'
import './design/tokens.css'
import './styles.css'

const isGallery = new URLSearchParams(window.location.search).has('gallery')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isGallery ? <Gallery /> : <App />}
  </React.StrictMode>,
)

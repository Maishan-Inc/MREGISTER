import React from 'react';
import { createRoot } from 'react-dom/client';
import './app.css';
import { APP_CONFIG } from './config.js';
import { AuthScreen } from './ui.jsx';
import { ConsoleApp } from './console.jsx';

function App() {
  if (APP_CONFIG.authView !== 'app') {
    return <AuthScreen view={APP_CONFIG.authView} />;
  }
  return <ConsoleApp />;
}

createRoot(document.getElementById('root')).render(<App />);

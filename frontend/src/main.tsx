import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/outfit';
import '@fontsource-variable/geist';
import '@fontsource/space-mono/400.css';
import '@fontsource/space-mono/700.css';
import './styles/app.css';
import App from './App';

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
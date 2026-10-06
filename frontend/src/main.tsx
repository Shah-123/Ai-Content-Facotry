import {StrictMode, useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {MotionConfig} from 'motion/react';
import App from './App.tsx';
import {AuthView} from './components/AuthView.tsx';
import {APIClient, AuthUser} from './api.ts';
import {useTheme} from './hooks/useTheme.ts';
import './index.css';

/** Login screen until the stored token checks out; then the dashboard.
 *  Gating here rather than inside App keeps App's job polling and WebSocket
 *  from ever running for a signed-out visitor. */
function AuthGate() {
  // undefined = still validating the stored token, null = signed out.
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);
  // Applies <html data-theme>. TopNav's own useTheme only mounts once signed
  // in, which left the login screen dark for light-theme users.
  useTheme();

  useEffect(() => {
    APIClient.me().then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined) {
    return (
      <div className="min-h-dvh flex items-center justify-center text-sm font-medium text-base-400 noise-bg ambient-bg">
        Checking your session…
      </div>
    );
  }
  return user ? <App /> : <AuthView onAuthed={setUser} />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* reducedMotion="user" makes every motion component follow the OS
        setting, matching the CSS block in index.css. */}
    <MotionConfig reducedMotion="user">
      <AuthGate />
    </MotionConfig>
  </StrictMode>,
);

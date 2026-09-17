import { useState } from 'react';
import { motion } from 'motion/react';
import { Eye, EyeOff, Loader2, Lock, Mail, Sparkles, User } from 'lucide-react';
import { APIClient, AuthUser } from '../api';

/** Mirrors MIN_PASSWORD_LENGTH in Agents_backend/api/users.py. */
const MIN_PASSWORD_LENGTH = 8;

const PITCH = [
  'Plan, research and draft with a multi-agent graph',
  'Human-in-the-loop outline approval before writing',
  'Podcast, video and campaign assets from one run',
];

interface AuthViewProps {
  onAuthed: (user: AuthUser) => void;
}

/**
 * Login + sign-up, one component with a mode switch — the two forms differ by
 * two fields, so splitting them into separate pages would duplicate the whole
 * layout to change a heading.
 */
export function AuthView({ onAuthed }: AuthViewProps) {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const isSignup = mode === 'signup';

  const switchMode = (next: 'login' | 'signup') => {
    setMode(next);
    setError('');
    setConfirm('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    // Checked here as well as on the server: a mismatched confirmation is
    // never sent, and the server never sees the second copy.
    if (isSignup && password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const user = isSignup
        ? await APIClient.signUp(email, password, name)
        : await APIClient.logIn(email, password);
      onAuthed(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh flex antialiased relative noise-bg ambient-bg">
      {/* Brand panel — decorative, so it steps aside on small screens. */}
      <aside className="hidden lg:flex flex-col justify-between w-[46%] max-w-xl p-12 border-r border-white/6 relative z-10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl btn-primary flex items-center justify-center">
            <Sparkles className="w-4.5 h-4.5" aria-hidden="true" />
          </div>
          <span className="text-base font-extrabold text-gradient-amber tracking-tight">
            AI Content Factory
          </span>
        </div>

        <div>
          <h1 className="text-4xl font-extrabold text-base-100 leading-tight tracking-tight">
            One topic in.<br />A finished campaign out.
          </h1>
          <ul className="mt-8 space-y-3">
            {PITCH.map(line => (
              <li key={line} className="flex items-start gap-3 text-sm text-base-400">
                <span className="w-1.5 h-1.5 mt-1.5 rounded-full bg-accent-400 shrink-0" />
                {line}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-base-500">
          Research · Writing · QA · Multimedia — orchestrated by LangGraph.
        </p>
      </aside>

      {/* Form panel */}
      <main className="flex-1 flex items-center justify-center p-6 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel w-full max-w-md rounded-2xl p-8"
        >
          <div className="lg:hidden flex items-center gap-2.5 mb-6">
            <div className="w-8 h-8 rounded-xl btn-primary flex items-center justify-center">
              <Sparkles className="w-4 h-4" aria-hidden="true" />
            </div>
            <span className="text-sm font-extrabold text-gradient-amber tracking-tight">
              AI Content Factory
            </span>
          </div>

          <h2 className="text-2xl font-bold text-base-100 tracking-tight">
            {isSignup ? 'Create your account' : 'Welcome back'}
          </h2>
          <p className="text-sm text-base-500 mt-1.5">
            {isSignup
              ? 'Set up an account to start generating content.'
              : 'Sign in to pick up where the agents left off.'}
          </p>

          {/* Mode switch */}
          <div
            role="tablist"
            aria-label="Authentication mode"
            className="mt-6 grid grid-cols-2 gap-1 p-1 rounded-xl glass-pill"
          >
            {(['login', 'signup'] as const).map(m => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => switchMode(m)}
                className={`py-2 rounded-lg text-xs font-bold uppercase tracking-wider transition-colors ${
                  mode === m
                    ? 'bg-accent-500/15 text-accent-400 border border-accent-500/25'
                    : 'text-base-500 hover:text-base-300 border border-transparent'
                }`}
              >
                {m === 'login' ? 'Sign in' : 'Sign up'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            {isSignup && (
              <Field label="Name" icon={<User className="w-4 h-4" aria-hidden="true" />} htmlFor="auth-name">
                <input
                  id="auth-name"
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  autoComplete="name"
                  placeholder="Ada Lovelace"
                  className={INPUT_CLASS}
                />
              </Field>
            )}

            <Field label="Email" icon={<Mail className="w-4 h-4" aria-hidden="true" />} htmlFor="auth-email">
              <input
                id="auth-email"
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="you@example.com"
                className={INPUT_CLASS}
              />
            </Field>

            <Field label="Password" icon={<Lock className="w-4 h-4" aria-hidden="true" />} htmlFor="auth-password">
              <div className="relative">
                <input
                  id="auth-password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  autoComplete={isSignup ? 'new-password' : 'current-password'}
                  placeholder={isSignup ? `At least ${MIN_PASSWORD_LENGTH} characters` : '••••••••'}
                  className={`${INPUT_CLASS} pr-10`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg text-base-500 hover:text-base-200 hover:bg-white/5 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </Field>

            {isSignup && (
              <Field label="Confirm password" icon={<Lock className="w-4 h-4" aria-hidden="true" />} htmlFor="auth-confirm">
                <input
                  id="auth-confirm"
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  placeholder="Repeat the password"
                  className={INPUT_CLASS}
                />
              </Field>
            )}

            {error && (
              <p
                role="alert"
                className="text-xs text-signal-error bg-signal-error-dim border border-signal-error/20 rounded-xl px-3 py-2.5"
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="kinetic-pill w-full py-2.5 rounded-xl text-sm flex items-center justify-center gap-2"
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
              {busy
                ? (isSignup ? 'Creating account…' : 'Signing in…')
                : (isSignup ? 'Create account' : 'Sign in')}
            </button>
          </form>

          <p className="mt-5 text-center text-xs text-base-500">
            {isSignup ? 'Already have an account?' : 'No account yet?'}{' '}
            <button
              type="button"
              onClick={() => switchMode(isSignup ? 'login' : 'signup')}
              className="font-semibold text-accent-400 hover:text-accent-300 transition-colors"
            >
              {isSignup ? 'Sign in' : 'Create one'}
            </button>
          </p>
        </motion.div>
      </main>
    </div>
  );
}

const INPUT_CLASS =
  'w-full bg-base-900 border border-white/8 rounded-xl px-3 py-2.5 text-sm text-base-100 ' +
  'placeholder:text-base-600 focus:outline-none focus:border-accent-500/40 transition-colors';

function Field({
  label, icon, htmlFor, children,
}: {
  label: string;
  icon: React.ReactNode;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="text-label font-bold text-base-400 uppercase tracking-wider mb-1.5 flex items-center gap-1.5"
      >
        <span className="text-base-500">{icon}</span>
        {label}
      </label>
      {children}
    </div>
  );
}

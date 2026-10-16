import { useState } from 'react';
import { motion } from 'motion/react';
import {
  Check, Eye, EyeOff, FileText, ListOrdered, Loader2, Search, ShieldAlert, Sparkles,
} from 'lucide-react';
import { APIClient, AuthUser } from '../api';

/** Mirrors MIN_PASSWORD_LENGTH in Agents_backend/api/users.py. */
const MIN_PASSWORD_LENGTH = 8;

const PITCH = [
  'Plan, research and draft with a multi-agent graph',
  'Human-in-the-loop outline approval before writing',
  'Podcast, video and campaign assets from one run',
];

/** Static product proof for the brand panel: plain constants, no data or state. */
const PROOF = [
  { agent: 'Research', icon: Search,      dot: 'bg-sky-600 dark:bg-sky-400',         message: 'Found 14 sources',    time: '14:02:07' },
  { agent: 'Plan',     icon: ListOrdered, dot: 'bg-violet-600 dark:bg-violet-400',   message: 'Outline: 8 sections', time: '14:02:31' },
  { agent: 'Writer',   icon: FileText,    dot: 'bg-amber-600 dark:bg-amber-400',     message: 'Section 3 of 8…',     time: '14:03:12', live: true },
  { agent: 'QA',       icon: ShieldAlert, dot: 'bg-emerald-600 dark:bg-emerald-400', message: 'Waiting',             time: '—',        pending: true },
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

  // Two tabs, so either arrow key moves to the other one.
  const handleTabKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const next = isSignup ? 'login' : 'signup';
    switchMode(next);
    document.getElementById(`auth-tab-${next}`)?.focus();
  };

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr] bg-canvas">
      {/* Brand panel — decorative, so it steps aside on small screens. */}
      <aside className="relative hidden lg:flex flex-col justify-between overflow-hidden border-r border-line bg-surface p-12">
        <Brand />

        <div>
          <h1 className="font-serif text-display text-base-50 text-balance">
            One topic in.<br /><em className="italic">A finished campaign out.</em>
          </h1>
          <ul className="mt-8 space-y-3">
            {PITCH.map(line => (
              <li key={line} className="flex gap-2.5 text-sm text-base-300">
                <Check className="size-4 mt-0.5 shrink-0 text-base-500" aria-hidden="true" />
                {line}
              </li>
            ))}
          </ul>

          {/* Product proof: a static mini timeline. */}
          <div
            aria-hidden="true"
            className="hidden roomy:block surface-raised mt-8 w-full max-w-[460px] p-4 [mask-image:linear-gradient(to_bottom,black_70%,transparent)]"
          >
            <ol className="relative before:absolute before:left-[11px] before:top-3 before:bottom-3 before:w-px before:bg-line">
              {PROOF.map(row => (
                <li key={row.agent}>
                  <div className="relative flex h-8 items-center gap-2.5 mt-3 first:mt-0">
                    <span className="relative z-10 grid size-6 place-items-center rounded-full bg-base-800 ring-1 ring-line-strong">
                      <row.icon className="size-3.5 text-base-300" />
                    </span>
                    <span className={`size-1.5 rounded-full ${row.dot}`} />
                    <span className="text-ui font-medium text-base-100">{row.agent}</span>
                  </div>
                  <div className={`flex items-baseline gap-3 rounded-lg py-1 pl-9 pr-2 ${row.live ? 'bg-hover' : ''}`}>
                    <p className="flex-1 text-ui text-base-300">
                      {row.live && <Loader2 className="mr-1.5 inline size-3.5 animate-spin text-accent-400 align-[-2px]" />}
                      {row.pending && <span className="dot dot-pending mr-1.5 inline-block align-middle" />}
                      {row.message}
                    </p>
                    <span className="shrink-0 font-mono text-xs text-base-500 tabular-nums">{row.time}</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <p className="text-xs text-base-500">
          Research · Writing · QA · Multimedia — orchestrated by LangGraph.
        </p>
      </aside>

      {/* Form panel */}
      <main className="flex items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-sm"
        >
          <div className="lg:hidden mb-8">
            <Brand />
          </div>

          <h2 className="text-title-sm font-serif text-base-50">
            {isSignup ? 'Create your account' : 'Welcome back'}
          </h2>
          <p className="mt-1 text-sm text-base-400">
            {isSignup
              ? 'Set up an account to start generating content.'
              : 'Sign in to pick up where the agents left off.'}
          </p>

          {/* Mode switch */}
          <div
            role="tablist"
            aria-label="Authentication mode"
            onKeyDown={handleTabKey}
            className="mt-8 seg w-full"
          >
            {(['login', 'signup'] as const).map(m => (
              <button
                key={m}
                id={`auth-tab-${m}`}
                type="button"
                role="tab"
                aria-selected={mode === m}
                tabIndex={mode === m ? 0 : -1}
                onClick={() => switchMode(m)}
                className="seg-item transition-colors"
              >
                {m === 'login' ? 'Sign in' : 'Sign up'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} role="tabpanel" aria-labelledby={`auth-tab-${mode}`} className="mt-6">
            <div className="space-y-4">
              {isSignup && (
                <Field label="Name" htmlFor="auth-name">
                  <input
                    id="auth-name"
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    autoComplete="name"
                    placeholder="Ada Lovelace"
                    className="field field-lg"
                  />
                </Field>
              )}

              <Field label="Email" htmlFor="auth-email">
                <input
                  id="auth-email"
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="you@example.com"
                  className="field field-lg"
                />
              </Field>

              <Field label="Password" htmlFor="auth-password">
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
                    className="field field-lg pr-11"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(v => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    title={showPassword ? 'Hide password' : 'Show password'}
                    className="btn btn-ghost btn-icon btn-sm absolute right-1.5 top-1/2 -translate-y-1/2"
                  >
                    {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </button>
                </div>
              </Field>

              {isSignup && (
                <Field label="Confirm password" htmlFor="auth-confirm">
                  <input
                    id="auth-confirm"
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                    autoComplete="new-password"
                    placeholder="Repeat the password"
                    className="field field-lg"
                  />
                </Field>
              )}
            </div>

            {error && (
              <p
                role="alert"
                className="mt-4 rounded-lg bg-signal-error-dim px-3 py-2 text-ui text-signal-error"
              >
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="btn btn-primary btn-lg w-full mt-6"
            >
              {busy && <Loader2 className="animate-spin" aria-hidden="true" />}
              {busy
                ? (isSignup ? 'Creating account…' : 'Signing in…')
                : (isSignup ? 'Create account' : 'Sign in')}
            </button>
          </form>

          <p className="mt-6 text-center text-ui text-base-400">
            {isSignup ? 'Already have an account?' : 'No account yet?'}{' '}
            <button
              type="button"
              onClick={() => switchMode(isSignup ? 'login' : 'signup')}
              className="font-medium text-accent-400 hover:text-accent-300 transition-colors"
            >
              {isSignup ? 'Sign in' : 'Create one'}
            </button>
          </p>
        </motion.div>
      </main>
    </div>
  );
}

/** Brand mark + wordmark (the Sidebar recipe). The tile is static, not a button. */
function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid size-7 place-items-center rounded-lg bg-accent-500 text-on-accent">
        <Sparkles className="size-4" aria-hidden="true" />
      </div>
      <span className="text-ui font-semibold tracking-[-0.01em] text-base-50">
        AI Content Factory
      </span>
    </div>
  );
}

function Field({
  label, htmlFor, children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="field-label">
        {label}
      </label>
      {children}
    </div>
  );
}

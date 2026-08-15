import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

/**
 * Minimal toast notifications.
 *
 * Module-level store rather than a React context: `toast.error(...)` is callable
 * from hooks, API catch blocks, and plain functions without threading a provider
 * through the tree. Render <Toasts /> once at the app root.
 *
 * Replaces the previous pattern of swallowing failures into console.error, where
 * a failed job creation or plan approval left the user staring at a frozen UI.
 */

type ToastKind = 'error' | 'success' | 'info';

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

const AUTO_DISMISS_MS: Record<ToastKind, number> = {
  // Errors stay until dismissed — they usually need the user to do something.
  error: 0,
  success: 4000,
  info: 5000,
};

let nextId = 0;
let items: ToastItem[] = [];
let listeners: Array<(next: ToastItem[]) => void> = [];

const publish = () => listeners.forEach(listener => listener([...items]));

const dismiss = (id: number) => {
  items = items.filter(item => item.id !== id);
  publish();
};

const push = (kind: ToastKind, message: string) => {
  const id = nextId++;
  items = [...items, { id, kind, message }];
  publish();
  const ttl = AUTO_DISMISS_MS[kind];
  if (ttl > 0) setTimeout(() => dismiss(id), ttl);
  return id;
};

/** Extract a readable message from whatever a catch block received. */
const messageFrom = (error: unknown, fallback: string): string => {
  if (typeof error === 'string' && error.trim()) return error;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
};

export const toast = {
  error: (message: string) => push('error', message),
  success: (message: string) => push('success', message),
  info: (message: string) => push('info', message),
  dismiss,
  /** Log to console for debugging AND surface it to the user. */
  fromError: (error: unknown, fallback: string) => {
    console.error(fallback, error);
    return push('error', messageFrom(error, fallback));
  },
};

const STYLES: Record<ToastKind, { icon: typeof Info; ring: string; tint: string; fg: string }> = {
  error: { icon: AlertTriangle, ring: 'border-signal-error/30', tint: 'bg-signal-error-dim', fg: 'text-signal-error' },
  success: { icon: CheckCircle2, ring: 'border-signal-success/30', tint: 'bg-signal-success-dim', fg: 'text-signal-success' },
  info: { icon: Info, ring: 'border-signal-info/30', tint: 'bg-signal-info-dim', fg: 'text-signal-info' },
};

export function Toasts() {
  const [visible, setVisible] = useState<ToastItem[]>([]);

  useEffect(() => {
    listeners.push(setVisible);
    setVisible([...items]);
    return () => {
      listeners = listeners.filter(listener => listener !== setVisible);
    };
  }, []);

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="fixed bottom-4 right-4 z-[200] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
    >
      <AnimatePresence initial={false}>
        {visible.map(item => {
          const { icon: Icon, ring, tint, fg } = STYLES[item.kind];
          return (
            <motion.div
              key={item.id}
              layout
              initial={{ opacity: 0, y: 12, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.97 }}
              transition={{ duration: 0.18 }}
              role={item.kind === 'error' ? 'alert' : 'status'}
              className={`glass-panel flex items-start gap-3 rounded-xl border ${ring} ${tint} p-3 shadow-xl backdrop-blur-md`}
            >
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${fg}`} aria-hidden="true" />
              <p className="flex-1 text-[13px] leading-relaxed text-base-100 break-words">
                {item.message}
              </p>
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                aria-label="Dismiss notification"
                className="rounded-md p-0.5 text-base-500 transition-colors hover:bg-white/5 hover:text-base-100"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

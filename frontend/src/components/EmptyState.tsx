import React from 'react';
import { Sparkles } from 'lucide-react';

export function EmptyState({
  icon,
  title,
  description,
  onGenerate,
  error,
  actionLabel = 'Generate',
  hint,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  onGenerate?: () => void;
  error?: string | null;
  actionLabel?: string;
  hint?: string;
}) {
  return (
    <div className="well mx-auto flex min-h-[280px] w-full max-w-xl flex-col items-center justify-center px-8 py-14 text-center">
      <div className="mb-4 grid size-10 place-items-center rounded-lg bg-hover ring-1 ring-line text-base-300 [&_svg]:size-5">{icon}</div>
      <h3 className="text-heading text-base-50">{title}</h3>
      <p className="mt-1.5 max-w-sm text-ui text-base-400">{description}</p>
      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-signal-error-dim px-3 py-2 text-left text-ui text-signal-error">{error}</p>
      )}
      {onGenerate && (
        <button type="button" onClick={onGenerate} className="btn btn-primary mt-6">
          <Sparkles />
          {actionLabel}
        </button>
      )}
      {hint && <p className="mt-2 text-xs text-base-500">{hint}</p>}
    </div>
  );
}

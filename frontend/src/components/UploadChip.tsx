import { FileText, X, Loader2, Sparkles, Globe, BookOpen } from 'lucide-react';
import { SourceMode, UploadResult } from '../api';

interface UploadChipProps {
  status: 'uploading' | 'ready' | 'error';
  filename?: string;
  result?: UploadResult | null;
  errorMessage?: string;
  sourceMode: SourceMode;
  onSourceModeChange: (mode: SourceMode) => void;
  onClear: () => void;
}

const MODE_OPTIONS: Array<{
  id: SourceMode;
  label: string;
  desc: string;
  icon: typeof BookOpen;
}> = [
  { id: 'closed_book', label: 'Document only',  desc: 'Write strictly from this file. No web research.', icon: BookOpen },
  { id: 'hybrid',      label: 'Document + web', desc: 'Combine document facts with fresh web research.', icon: Globe },
  { id: 'auto_topic',  label: 'Auto-topic',     desc: 'Derive the title from the document, then research.', icon: Sparkles },
];

function _humanBytes(n: number): string {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 ? 0 : 1)} ${units[i]}`;
}

export function UploadChip({
  status, filename, result, errorMessage,
  sourceMode, onSourceModeChange, onClear,
}: UploadChipProps) {
  const displayName = result?.filename || filename || 'document';
  const isError = status === 'error';
  const isUploading = status === 'uploading';

  const activeMode = MODE_OPTIONS.find(opt => opt.id === sourceMode);

  return (
    <div className="flex flex-col gap-2 px-2 pt-1">
      {/* File chip */}
      <div className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs ring-1 ${
        isError ? 'bg-signal-error-dim ring-signal-error/25 text-signal-error' : 'bg-hover ring-line text-base-200'
      }`}>
        {isUploading
          ? <Loader2 className="size-3.5 shrink-0 animate-spin text-base-400" />
          : <FileText className={`size-3.5 shrink-0 ${isError ? 'text-signal-error' : 'text-base-400'}`} />}
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate text-base-100">{displayName}</div>
          <div className={`text-xs truncate ${isError ? 'text-signal-error' : 'text-base-500'}`} aria-live="polite">
            {isError && errorMessage}
            {isUploading && 'Parsing & extracting evidence...'}
            {status === 'ready' && result && (
              <>
                {result.format?.toUpperCase()} · {_humanBytes(result.bytes)} · {result.pages} page{result.pages !== 1 ? 's' : ''} · {result.evidence_count} fact{result.evidence_count !== 1 ? 's' : ''}
                {result.truncated && <span className="text-signal-warning ml-1.5">· truncated</span>}
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="btn btn-ghost btn-icon btn-sm shrink-0"
          aria-label="Remove file"
          title="Remove file"
        >
          <X />
        </button>
      </div>

      {/* Source-mode toggle (only meaningful once the upload is ready) */}
      {status === 'ready' && (
        <div>
          <div className="seg max-w-full" role="group" aria-label="How to use the document">
            {MODE_OPTIONS.map(opt => {
              const Icon = opt.icon;
              const active = sourceMode === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onSourceModeChange(opt.id)}
                  title={opt.desc}
                  aria-pressed={active}
                  className="seg-item !h-7 !text-xs whitespace-nowrap max-sm:!px-1.5 inline-flex items-center justify-center gap-1.5 transition-colors"
                >
                  <Icon className="hidden sm:block size-3.5" />
                  {opt.label}
                </button>
              );
            })}
          </div>
          {activeMode && <p className="mt-1 text-xs text-base-500">{activeMode.desc}</p>}
        </div>
      )}
    </div>
  );
}

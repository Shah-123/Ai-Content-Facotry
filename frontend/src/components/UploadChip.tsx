import { FileText, X, RefreshCw, Sparkles, Globe, BookOpen } from 'lucide-react';
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

  return (
    <div className="flex flex-col gap-2 px-1">
      {/* File chip */}
      <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs ${
        isError
          ? 'border-signal-error/30 bg-signal-error-dim text-signal-error'
          : 'border-white/10 bg-base-800/80 text-base-200'
      }`}>
        <div className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 ${
          isError ? 'bg-signal-error/10' : 'bg-accent-500/10'
        }`}>
          {isUploading
            ? <RefreshCw className="w-3.5 h-3.5 text-accent-400 animate-spin" />
            : <FileText className={`w-3.5 h-3.5 ${isError ? 'text-signal-error' : 'text-accent-400'}`} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate text-base-100">{displayName}</div>
          <div className="text-[11px] text-base-500 truncate">
            {isError && errorMessage}
            {isUploading && 'Parsing & extracting evidence...'}
            {status === 'ready' && result && (
              <>
                {result.format?.toUpperCase()} • {_humanBytes(result.bytes)} • {result.pages} page{result.pages !== 1 ? 's' : ''} • {result.evidence_count} fact{result.evidence_count !== 1 ? 's' : ''}
                {result.truncated && <span className="text-signal-warn ml-1.5">• truncated</span>}
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="p-1 rounded hover:bg-white/10 text-base-400 hover:text-base-100 shrink-0"
          aria-label="Remove file"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Source-mode toggle (only meaningful once the upload is ready) */}
      {status === 'ready' && (
        <div className="flex flex-wrap gap-1.5">
          {MODE_OPTIONS.map(opt => {
            const Icon = opt.icon;
            const active = sourceMode === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => onSourceModeChange(opt.id)}
                title={opt.desc}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all ${
                  active
                    ? 'text-accent-400 bg-accent-500/10 border-accent-500/30'
                    : 'text-base-400 hover:text-base-200 border-white/6 hover:bg-white/3'
                }`}
              >
                <Icon className="w-3 h-3" />
                {opt.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

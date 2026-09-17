import { motion } from 'motion/react';
import { ShieldCheck, RefreshCw, Sparkles, AlertTriangle } from 'lucide-react';
import { Job } from '../api';

/** QA audit panel. The re-run wires to POST /api/jobs/{id}/run-qa, which
    re-audits the CURRENT saved article and, on NEEDS_REVISION, runs one
    revision pass and re-audits — it does not regenerate the blog. */
export function QAAuditSection({
  currentJob,
  isRunning,
  onRun,
}: {
  currentJob: Job;
  isRunning: boolean;
  onRun: () => void;
}) {
  const score = currentJob.qa_score;
  const verdict = currentJob.qa_verdict;
  const hasScore = typeof score === 'number';
  const needsRevision = verdict === 'NEEDS_REVISION';

  // The raw qa_report.txt dump is deliberately NOT rendered here: it is an
  // internal audit trail (model-written prose, weights, per-issue fix notes),
  // not something the reader of a finished article should be handed. The score
  // and verdict badges above are the whole user-facing result; the full text
  // stays on disk and behind GET /api/jobs/{id}/qa-report.

  return (
    <div className="glass-panel rounded-2xl border border-white/6 overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-5 border-b border-white/5 bg-gradient-to-r from-accent-500/5 via-transparent to-transparent">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent-500/10 border border-accent-500/20 flex items-center justify-center shrink-0">
            <ShieldCheck className="w-5 h-5 text-accent-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-base-50 flex items-center gap-2 flex-wrap">
              QA Audit
              {hasScore && (
                <span className="text-xs font-mono font-bold text-accent-300 bg-accent-500/10 border border-accent-500/20 px-1.5 py-0.5 rounded">
                  {score!.toFixed(1)} / 10
                </span>
              )}
              {verdict && (
                <span
                  className={`text-label font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider border ${
                    needsRevision
                      ? 'text-signal-warning bg-signal-warning-dim border-signal-warning/20'
                      : 'text-accent-300 bg-accent-500/10 border-accent-500/20'
                  }`}
                >
                  {needsRevision ? 'Needs revision' : 'Ready'}
                </span>
              )}
            </h3>
            <p className="text-xs text-base-400 mt-0.5 leading-relaxed max-w-xl">
              Fact, structure and readability audit of the article as it stands now. Re-running
              audits the saved text and, if it comes back NEEDS_REVISION, applies one revision
              pass and re-audits. It does not rewrite the blog from scratch.
            </p>
          </div>
        </div>
        <motion.button
          onClick={onRun}
          disabled={isRunning}
          className={`btn-primary px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 shrink-0 self-start sm:self-center ${
            isRunning ? 'opacity-60 cursor-wait' : ''
          }`}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          {isRunning ? (
            <><RefreshCw className="w-4 h-4 animate-spin" /> Auditing...</>
          ) : hasScore ? (
            <><RefreshCw className="w-4 h-4" /> Re-run QA</>
          ) : (
            <><Sparkles className="w-4 h-4" /> Run QA</>
          )}
        </motion.button>
      </div>

      <div className="p-5">
        {isRunning ? (
          <div className="flex flex-col items-center gap-3 py-8 text-sm text-base-400">
            <div className="orbital-loader" style={{ width: '48px', height: '48px' }}>
              <div className="orbital-ring orbital-ring-1" />
              <div className="orbital-ring orbital-ring-2" />
            </div>
            <p className="mt-2">Re-auditing the article (plus one revision pass if needed)...</p>
          </div>
        ) : !hasScore ? (
          <p className="text-center py-8 text-sm text-base-400">
            Not audited yet. Click <strong className="text-accent-400">Run QA</strong> above to
            check the current article.
          </p>
        ) : needsRevision ? (
          <div className="flex items-start gap-2.5 p-3 rounded-xl bg-signal-warning-dim border border-signal-warning/15 text-xs text-base-200 leading-relaxed">
            <AlertTriangle className="w-4 h-4 text-signal-warning shrink-0 mt-px" />
            <span>
              At least one issue was marked <strong className="text-signal-warning">critical</strong>,
              so the pipeline runs a revision pass over the article before publishing.
            </span>
          </div>
        ) : (
          <p className="text-center py-2 text-sm text-base-400">
            Audit passed — no critical issues found.
          </p>
        )}
      </div>
    </div>
  );
}

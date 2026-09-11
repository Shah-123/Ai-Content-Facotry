import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { ShieldCheck, RefreshCw, Sparkles, AlertTriangle } from 'lucide-react';
import { APIClient, Job } from '../api';

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
  const [report, setReport] = useState('');

  // Refetch whenever the job or its score changes, so the text on screen
  // always belongs to the run the score came from.
  useEffect(() => {
    let stale = false;
    APIClient.getQAReport(currentJob.id)
      .then(text => { if (!stale) setReport(text); })
      .catch(() => { if (!stale) setReport(''); });
    return () => { stale = true; };
  }, [currentJob.id, currentJob.qa_score, isRunning]);

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
                <span className="text-[10px] font-mono font-bold text-accent-300 bg-accent-500/10 border border-accent-500/20 px-1.5 py-0.5 rounded">
                  {score!.toFixed(1)} / 10
                </span>
              )}
              {verdict && (
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider border ${
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
        ) : report ? (
          <>
            {needsRevision && (
              <div className="flex items-start gap-2.5 mb-4 p-3 rounded-xl bg-signal-warning-dim border border-signal-warning/15 text-xs text-base-200 leading-relaxed">
                <AlertTriangle className="w-4 h-4 text-signal-warning shrink-0 mt-px" />
                <span>
                  The verdict is set by the LLM auditor independently of the score. The pipeline
                  only loops back into a revision when at least one issue is marked{' '}
                  <strong className="text-signal-warning">critical</strong>.
                </span>
              </div>
            )}
            <pre className="text-[11px] text-base-300 leading-relaxed bg-base-950/40 p-4 rounded-xl border border-white/4 overflow-x-auto whitespace-pre-wrap font-mono">
              {report}
            </pre>
          </>
        ) : (
          <p className="text-center py-8 text-sm text-base-400">
            No QA report yet. Click <strong className="text-accent-400">Run QA</strong> above to
            audit the current article.
          </p>
        )}
      </div>
    </div>
  );
}

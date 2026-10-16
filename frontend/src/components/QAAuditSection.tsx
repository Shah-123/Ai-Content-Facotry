import { RefreshCw, Sparkles, AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import { Job } from '../api';

const QA_EXPLANATION =
  'Fact, structure and readability audit of the article as it stands now. Re-running audits the saved text and, if it comes back NEEDS_REVISION, applies one revision pass and re-audits. It does not rewrite the blog from scratch.';

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
    <section className="card p-6">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-medium text-base-500">QA score</h3>
        <button type="button" onClick={onRun} disabled={isRunning} className="ml-auto btn btn-secondary btn-sm">
          {isRunning ? (
            <><Loader2 className="animate-spin" /> Auditing…</>
          ) : hasScore ? (
            <><RefreshCw /> Re-run QA</>
          ) : (
            <><Sparkles /> Run QA</>
          )}
        </button>
      </div>

      <div className="mt-3 flex items-baseline gap-1">
        {hasScore ? (
          <>
            <span className="text-kpi text-base-50 tabular-nums">{score!.toFixed(1)}</span>
            <span className="text-sm text-base-500">/10</span>
          </>
        ) : (
          <span className="text-kpi text-base-500" aria-label="No score">—</span>
        )}
      </div>

      <div className="mt-2">
        {isRunning ? (
          <span className="badge" title="Re-auditing the article, plus one revision pass if needed">Re-auditing…</span>
        ) : !hasScore ? (
          <span className="badge">Not audited yet</span>
        ) : needsRevision ? (
          <span className="badge badge-warning">
            <AlertTriangle className="size-3.5" /> Needs revision
          </span>
        ) : (
          <span className="badge badge-success">
            <CheckCircle2 className="size-3.5" /> Passed · no critical issues
          </span>
        )}
      </div>

      {needsRevision && !isRunning && hasScore && (
        <p className="mt-2 text-xs text-base-400">
          At least one issue was marked critical, so the pipeline runs a revision pass over the article before publishing.
        </p>
      )}

      <p className="mt-3 text-xs leading-5 text-base-500">
        {QA_EXPLANATION}
      </p>
    </section>
  );
}

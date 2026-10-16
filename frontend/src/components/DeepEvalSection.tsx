import { RefreshCw, Sparkles, Loader2 } from 'lucide-react';
import { Job } from '../api';

const DEEPEVAL_EXPLANATION =
  'Official G-Eval implementation from Liu et al. 2023. Runs 4 LLM-judged rubrics with chain-of-thought scoring on a 0.0–1.0 scale. Costs ~4 extra GPT-4o calls — trigger only when you need a citable academic score. Not directly comparable to the 1–5 in-house score.';

/** KPI tile plus its rubric grid. Rendered as two siblings so the tile sits in
    the parent's 2-column KPI strip and the rubric grid spans the full row at
    the end of the panel (`@xl:col-span-2 order-last`). */
export function DeepEvalSection({
  currentJob,
  isRunning,
  onRun,
}: {
  currentJob: Job;
  isRunning: boolean;
  onRun: () => void;
}) {
  const de = currentJob.deepeval_scores;
  const rubrics = de
    ? [
        { title: 'Coherence (Structure & Flow)', short: 'Coherence', evaluation: de.coherence },
        { title: 'Relevance (Topic & Intent)', short: 'Relevance', evaluation: de.relevance },
        { title: 'Accuracy & Grounding', short: 'Accuracy', evaluation: de.accuracy },
        { title: 'Tone Alignment', short: 'Tone', evaluation: de.tone_alignment },
      ]
    : [];
  const lowest = rubrics
    .filter((r) => typeof r.evaluation?.score === 'number')
    .sort((a, b) => (a.evaluation.score as number) - (b.evaluation.score as number))[0];

  return (
    <>
      <section className="card p-6">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-medium text-base-500">G-Eval</h3>
          <span className="badge">deepeval</span>
          <button type="button" onClick={onRun} disabled={isRunning} className="ml-auto btn btn-secondary btn-sm">
            {isRunning ? (
              <><Loader2 className="animate-spin" /> Auditing…</>
            ) : de ? (
              <><RefreshCw /> Re-run audit</>
            ) : (
              <><Sparkles /> Run audit</>
            )}
          </button>
        </div>

        <div className="mt-3 flex items-baseline gap-1">
          {de && typeof de.overall_score === 'number' ? (
            <>
              <span className="text-kpi text-base-50 tabular-nums">{de.overall_score.toFixed(2)}</span>
              <span className="text-sm text-base-500">/1</span>
            </>
          ) : (
            <span className="text-kpi text-base-500">{de ? '—' : 'Not run'}</span>
          )}
        </div>

        {(isRunning && !de) || de ? (
          <p className="mt-2 text-xs text-base-400">
            {isRunning && !de
              ? 'Running 4 rubrics, about 30 s…'
              : lowest
                ? `Lowest: ${lowest.short} ${(lowest.evaluation.score as number).toFixed(2)}`
                : 'No rubric returned a score'}
          </p>
        ) : null}

        <p className="mt-3 text-xs leading-5 text-base-500">
          {DEEPEVAL_EXPLANATION}
        </p>
      </section>

      {de && (
        <section className="@xl:col-span-2 order-last mt-4">
          <h3 className="mb-3 text-xs font-medium text-base-500">deepeval rubrics · 0–1 scale</h3>
          <div className="grid gap-3 @2xl:grid-cols-2">
            {rubrics.map((r) => (
              <DeepEvalRubricCard key={r.title} title={r.title} evaluation={r.evaluation} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function DeepEvalRubricCard({
  title,
  evaluation,
}: {
  title: string;
  evaluation: { score: number | null; reasoning: string };
}) {
  const score = evaluation?.score;
  const pct = typeof score === 'number' ? Math.max(0, Math.min(1, score)) * 100 : 0;
  const hasScore = typeof score === 'number';

  return (
    <div className="card p-5 transition-colors hover:border-line-strong">
      <div className="flex items-center gap-3">
        <h4 className="min-w-0 text-ui font-semibold text-base-50 flex-1">{title}</h4>
        <span className={`font-mono text-[13px] tabular-nums ${hasScore ? 'text-base-100' : 'text-signal-error'}`}>
          {hasScore ? score!.toFixed(3) : 'N/A'}
        </span>
      </div>
      <div className="mt-3 h-1.5 w-full rounded-full bg-base-700 overflow-hidden" aria-hidden="true">
        <div className="h-full rounded-full bg-indicator" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-3 text-ui leading-6 text-base-300">
        {evaluation?.reasoning || 'No reasoning provided.'}
      </p>
    </div>
  );
}

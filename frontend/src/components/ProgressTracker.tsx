import { useMemo } from 'react';
import { Check, Loader2, X } from 'lucide-react';
import { AgentEvent } from '../api';

interface ProgressTrackerProps {
  events: AgentEvent[];
  jobStatus?: string;
  /** One-line dots variant for the sticky job bar. */
  compact?: boolean;
  className?: string;
}

/** Maps agent_name values to pipeline stages. */
// Keys MUST match the agent_name strings event_bus.emit() is actually called
// with. Half of them used to be node-function names (worker, merge_content,
// decide_images...) that no emit ever produced, so the Write stage never lit
// while the writers ran. ProgressTracker.test.ts pins the writing path.
const STAGE_MAP: Record<string, number> = {
  router: 0,
  ingest: 0,
  research: 0,
  orchestrator: 1,
  writer: 2,
  merger: 2,
  images: 2,
  qa_agent: 3,
  revision: 3,
  geval_evaluator: 4,
  deepeval_evaluator: 4,
  campaign_generator: 4,
  video: 4,
  podcast_generator: 4,
  // 'system' is deliberately unmapped: it fires "Pipeline started" at t=0,
  // which would light the final stage before any work has happened. The
  // jobStatus === 'completed' branch below handles the end of the run.
};

const STAGES = [
  { label: 'Research' },
  { label: 'Plan' },
  { label: 'Write' },
  { label: 'QA' },
  { label: 'Polish' },
] as const;

export function getStageStates(events: AgentEvent[], jobStatus?: string) {
  // Determine which stages have started, completed, or errored
  const stageHighest = new Array(STAGES.length).fill(-1); // -1=pending, 0=started, 1=completed, 2=error
  let activeStage = -1;

  for (const ev of events) {
    const idx = STAGE_MAP[ev.agent_name] ?? -1;
    if (idx < 0) continue;

    if (ev.status === 'error') {
      stageHighest[idx] = Math.max(stageHighest[idx], 2);
    } else if (ev.status === 'completed') {
      stageHighest[idx] = Math.max(stageHighest[idx], 1);
    } else {
      stageHighest[idx] = Math.max(stageHighest[idx], 0);
    }

    if (idx > activeStage && ev.status !== 'error') {
      activeStage = idx;
    }
  }

  // A live job with no mapped events yet (the pre-flight topic guard window)
  // still gets stage 0 lit, so the rail reads as "started" instead of dead.
  if (activeStage === -1 && jobStatus && jobStatus !== 'completed' && jobStatus !== 'failed') {
    activeStage = 0;
  }

  // If job completed, mark everything as complete
  if (jobStatus === 'completed') {
    for (let i = 0; i < stageHighest.length; i++) {
      if (stageHighest[i] < 1) stageHighest[i] = 1;
    }
    activeStage = STAGES.length; // past all
  }

  return stageHighest.map((state, idx) => {
    if (state === 2) return 'error' as const;
    if (state === 1) return 'completed' as const;
    if (state === 0 || idx === activeStage) return 'active' as const;
    return 'pending' as const;
  });
}

export function ProgressTracker({ events, jobStatus, compact, className = '' }: ProgressTrackerProps) {
  const states = useMemo(() => getStageStates(events, jobStatus), [events, jobStatus]);

  // Render as soon as a job exists — waiting for the first event kept the rail
  // hidden through the whole topic-guard + WS-connect window.
  if (events.length === 0 && !jobStatus) return null;

  if (compact) {
    const done = states.filter(s => s === 'completed').length;
    const cur = Math.max(states.lastIndexOf('active'), states.lastIndexOf('error'));
    const label = cur >= 0 ? STAGES[cur].label : done === STAGES.length ? 'Done' : STAGES[0].label;
    return (
      <div className={`flex items-center gap-1 ${className}`}>
        {states.map((state, idx) => (
          <span key={STAGES[idx].label} className="contents" aria-hidden="true">
            {idx > 0 && <span className="w-3 h-px bg-line-strong" />}
            <span className={`size-2 rounded-full ${
              state === 'completed' ? 'bg-signal-success'
              : state === 'active' ? 'live-dot'
              : state === 'error' ? 'bg-signal-error'
              : 'dot-pending'
            }`} />
          </span>
        ))}
        <span className="ml-2 text-xs text-base-400">{label} · {done}/{STAGES.length}</span>
      </div>
    );
  }

  return (
    <div className={`card px-4 py-3 ${className}`}>
      <ol className="flex items-start" aria-label="Pipeline progress">
        {STAGES.map((stage, idx) => {
          const state = states[idx];
          return (
            <li key={stage.label} className="contents">
              <div className="flex w-12 sm:w-16 shrink-0 flex-col items-center" aria-current={state === 'active' ? 'step' : undefined}>
                <span className={`step-node step-node-${state}`}>
                  {state === 'completed' ? <Check className="size-3" />
                    : state === 'active' ? <Loader2 className="size-3 animate-spin" />
                    : state === 'error' ? <X className="size-3" />
                    : idx + 1}
                </span>
                <span className={`mt-1.5 text-xs ${state === 'active' ? 'text-base-50 font-medium' : 'text-base-500'}`}>
                  {stage.label}
                  {state !== 'active' && <span className="sr-only">, {state}</span>}
                </span>
              </div>
              {idx < STAGES.length - 1 && (
                <span
                  aria-hidden="true"
                  className={`step-connector flex-1 mx-2 mt-3 ${state === 'completed' ? 'step-connector-fill' : ''}`}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

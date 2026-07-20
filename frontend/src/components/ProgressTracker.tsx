import { useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, Search, ListOrdered, PenTool, ShieldCheck, Sparkles, AlertTriangle } from 'lucide-react';
import { AgentEvent } from '../api';

interface ProgressTrackerProps {
  events: AgentEvent[];
  jobStatus?: string;
}

/** Maps agent_name values to pipeline stages. */
const STAGE_MAP: Record<string, number> = {
  router: 0,
  document_ingest: 0,
  research: 0,
  orchestrator: 1,
  worker: 2,
  merge_content: 2,
  decide_images: 2,
  generate_and_place_images: 2,
  completion_validator: 2,
  qa_agent: 3,
  revision: 3,
  keyword_optimizer: 4,
  blog_evaluator: 4,
  geval_evaluator: 4,
  campaign_generator: 4,
  video_generator: 4,
  podcast_generator: 4,
  system: 4,
};

const STAGES = [
  { label: 'Research', icon: Search },
  { label: 'Plan', icon: ListOrdered },
  { label: 'Write', icon: PenTool },
  { label: 'QA', icon: ShieldCheck },
  { label: 'Polish', icon: Sparkles },
] as const;

function getStageStates(events: AgentEvent[], jobStatus?: string) {
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

export function ProgressTracker({ events, jobStatus }: ProgressTrackerProps) {
  const states = useMemo(() => getStageStates(events, jobStatus), [events, jobStatus]);

  // Don't show if no events at all
  if (events.length === 0 && jobStatus !== 'completed') return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="w-full max-w-3xl mx-auto my-4"
    >
      <div className="glass-panel rounded-2xl p-5 border border-white/6">
        <div className="flex items-center justify-between mb-4 px-1">
          <span className="text-[10px] font-bold text-base-500 uppercase tracking-[0.15em]">Pipeline Progress</span>
          <div className="flex items-center gap-1.5">
            {states.filter(s => s === 'completed').length > 0 && (
              <span className="text-[10px] font-mono text-base-500">
                {states.filter(s => s === 'completed').length}/{STAGES.length}
              </span>
            )}
          </div>
        </div>
        <div className="step-track">
          {STAGES.map((stage, idx) => {
            const state = states[idx];
            const Icon = stage.icon;
            const nodeClass =
              state === 'completed' ? 'step-node step-node-completed'
              : state === 'active' ? 'step-node step-node-active'
              : state === 'error' ? 'step-node step-node-error'
              : 'step-node step-node-pending';

            return (
              <div key={stage.label} className="contents">
                <div className="flex flex-col items-center gap-1.5">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={state}
                      initial={{ scale: 0.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.6, opacity: 0 }}
                      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                      className={nodeClass}
                    >
                      {state === 'completed' ? (
                        <Check className="w-4 h-4" strokeWidth={3} />
                      ) : state === 'error' ? (
                        <AlertTriangle className="w-3.5 h-3.5" />
                      ) : (
                        <Icon className="w-3.5 h-3.5" />
                      )}
                    </motion.div>
                  </AnimatePresence>
                  <span className={`text-[10px] font-medium transition-colors ${
                    state === 'completed' ? 'text-signal-success'
                    : state === 'active' ? 'text-accent-400'
                    : state === 'error' ? 'text-signal-error'
                    : 'text-base-500'
                  }`}>
                    {stage.label}
                  </span>
                </div>
                {idx < STAGES.length - 1 && (
                  <div className="step-connector self-start mt-4">
                    <div
                      className="step-connector-fill"
                      style={{
                        transform: `scaleX(${
                          state === 'completed' ? 1
                          : state === 'active' ? 0.5
                          : 0
                        })`,
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}

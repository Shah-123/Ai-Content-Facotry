import React from 'react';
import { motion } from 'motion/react';
import { GraduationCap, RefreshCw, Sparkles } from 'lucide-react';
import { Job } from '../api';

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

  return (
    <div className="glass-panel rounded-2xl border border-white/6 overflow-hidden">
      {/* Header bar with trigger button */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-5 border-b border-white/5 bg-gradient-to-r from-accent-500/5 via-transparent to-transparent">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent-500/10 border border-accent-500/20 flex items-center justify-center shrink-0">
            <GraduationCap className="w-5 h-5 text-accent-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-base-50 flex items-center gap-2">
              Academic Audit
              <span className="text-[10px] font-semibold text-accent-300 bg-accent-500/10 border border-accent-500/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
                deepeval
              </span>
            </h3>
            <p className="text-xs text-base-400 mt-0.5 leading-relaxed max-w-xl">
              Official G-Eval implementation from Liu et al. 2023. Runs 4 LLM-judged rubrics with
              chain-of-thought scoring on a 0.0–1.0 scale. Costs ~4 extra GPT-4o calls — trigger
              only when you need a citable academic score.
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
            <>
              <RefreshCw className="w-4 h-4 animate-spin" /> Auditing...
            </>
          ) : de ? (
            <>
              <RefreshCw className="w-4 h-4" /> Re-run Audit
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" /> Run Academic Audit
            </>
          )}
        </motion.button>
      </div>

      {/* Body */}
      <div className="p-5">
        {de ? (
          <div>
            {/* Overall headline */}
            <div className="flex items-center gap-4 mb-6 p-4 rounded-xl bg-accent-500/[0.02] border border-accent-500/10 max-w-sm">
              {/* Animated Score Ring for DeepEval */}
              <div
                className="score-ring shrink-0"
                style={
                  {
                    '--score-pct':
                      typeof de.overall_score === 'number' ? de.overall_score * 100 : 0,
                    width: '64px',
                    height: '64px',
                  } as React.CSSProperties
                }
              >
                <div
                  className="score-ring-inner"
                  style={{ width: 'calc(100% - 6px)', height: 'calc(100% - 6px)' }}
                >
                  <motion.span
                    className="text-lg font-extrabold text-accent-400 leading-none"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4 }}
                  >
                    {typeof de.overall_score === 'number' ? de.overall_score.toFixed(2) : 'N/A'}
                  </motion.span>
                  <span className="text-[7px] text-base-500 font-semibold mt-0.5">/ 1.0</span>
                </div>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-base-500 uppercase tracking-wider mb-1">
                  Overall Academic Score
                </div>
                <div className="text-xs text-base-400 leading-relaxed">
                  Mean of 4 deepeval G-Eval rubrics. Not directly comparable to the 1–5 in-house
                  score.
                </div>
              </div>
            </div>

            {/* Four rubric cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <DeepEvalRubricCard title="Coherence (Structure & Flow)" evaluation={de.coherence} />
              <DeepEvalRubricCard title="Relevance (Topic & Intent)" evaluation={de.relevance} />
              <DeepEvalRubricCard title="Accuracy & Grounding" evaluation={de.accuracy} />
              <DeepEvalRubricCard title="Tone Alignment" evaluation={de.tone_alignment} />
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-sm text-base-400">
            {isRunning ? (
              <div className="flex flex-col items-center gap-3">
                <div className="orbital-loader" style={{ width: '48px', height: '48px' }}>
                  <div className="orbital-ring orbital-ring-1" />
                  <div className="orbital-ring orbital-ring-2" />
                </div>
                <p className="mt-2">Running official deepeval G-Eval (4 rubrics, ~30s)...</p>
              </div>
            ) : (
              <p>
                No academic audit yet. Click{' '}
                <strong className="text-accent-400">Run Academic Audit</strong> above to
                cross-validate the in-house G-Eval with the official deepeval implementation.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
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
    <motion.div
      className="bg-white/[0.02] border border-white/5 rounded-xl p-4 hover-lift"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <h4 className="font-semibold text-xs text-base-100">{title}</h4>
        <span
          className={`text-xs font-mono font-bold ${
            hasScore ? 'text-accent-400' : 'text-signal-error'
          }`}
        >
          {hasScore ? score!.toFixed(3) : 'N/A'}
        </span>
      </div>
      {/* Animated Progress bar (0-1 scale visualization) */}
      <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden mb-3">
        <motion.div
          className="h-full bg-gradient-to-r from-accent-500/60 to-accent-400 rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
      <p className="text-[11px] text-base-300 leading-relaxed bg-base-950/40 p-2.5 rounded-lg border border-white/4">
        {evaluation?.reasoning || 'No reasoning provided.'}
      </p>
    </motion.div>
  );
}

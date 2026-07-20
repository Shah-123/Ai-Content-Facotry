import React from 'react';
import { motion } from 'motion/react';

export function RubricDetailCard({
  metricKey,
  title,
  evaluation,
  hoveredKey,
  setHoveredKey,
}: {
  metricKey: string;
  title: string;
  evaluation: { score: number; reasoning: string };
  hoveredKey: string | null;
  setHoveredKey: (k: string | null) => void;
}) {
  const isHovered = hoveredKey === metricKey;

  return (
    <motion.div
      onMouseEnter={() => setHoveredKey(metricKey)}
      onMouseLeave={() => setHoveredKey(null)}
      className={`glass-panel p-5 rounded-2xl border transition-all duration-300 ${
        isHovered
          ? 'border-accent-500/50 bg-accent-500/[0.03] translate-x-1 shadow-[0_4px_20px_var(--color-accent-glow)]'
          : 'border-white/5 bg-white/[0.01]'
      }`}
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
        <h4
          className={`font-semibold text-sm transition-colors ${
            isHovered ? 'text-accent-400 font-bold' : 'text-base-100'
          }`}
        >
          {title}
        </h4>

        {/* Rating Boxes (1 to 5) */}
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((lvl) => {
            const active = lvl <= evaluation.score;
            return (
              <motion.span
                key={lvl}
                className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold border transition-all ${
                  active
                    ? 'bg-accent-500/20 border-accent-500/40 text-accent-400 shadow-[0_0_8px_var(--color-accent-glow)]'
                    : 'bg-white/2 border-white/5 text-base-500'
                }`}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: lvl * 0.05, type: 'spring', stiffness: 300 }}
              >
                {lvl}
              </motion.span>
            );
          })}
        </div>
      </div>
      <p className="text-xs text-base-300 leading-relaxed bg-base-950/40 p-3.5 rounded-xl border border-white/4">
        {evaluation.reasoning}
      </p>
    </motion.div>
  );
}

import React from 'react';
import { motion } from 'motion/react';
import { LayoutTemplate } from 'lucide-react';

export function EmptyState({
  icon,
  title,
  description,
  onGenerate,
  error,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  onGenerate: () => void;
  error?: string | null;
}) {
  return (
    <div className="glass-panel p-12 rounded-2xl flex flex-col items-center justify-center text-center min-h-[400px] border border-white/4 relative overflow-hidden group max-w-3xl mx-auto">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] bg-accent-500/5 rounded-full blur-3xl group-hover:bg-accent-500/10 transition-all duration-700"></div>

      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 20 }}
        className="relative z-10 w-24 h-24 bg-base-900 rounded-full flex items-center justify-center mb-6 shadow-xl border border-white/6 text-accent-400 group-hover:scale-105 transition-transform duration-500"
      >
        {icon}
      </motion.div>
      <h3 className="text-2xl font-bold text-base-50 mb-3">{title}</h3>
      <p className="text-base-400 mb-8 max-w-md text-sm leading-relaxed">{description}</p>

      {error && (
        <div className="mb-8 p-4 rounded-xl bg-signal-error-dim/20 border border-signal-error/20 text-signal-error text-xs max-w-md flex items-center gap-3 relative z-10">
          <div className="w-2 h-2 rounded-full bg-signal-error animate-pulse shrink-0"></div>
          <span className="text-left font-medium">{error}</span>
        </div>
      )}

      <motion.button
        onClick={onGenerate}
        className="btn-primary px-8 py-3.5 rounded-xl font-bold shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_30px_rgba(245,158,11,0.4)] hover:-translate-y-1 transition-all flex items-center gap-2 z-10"
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.97 }}
      >
        <LayoutTemplate className="w-5 h-5" /> Generate Now
      </motion.button>
    </div>
  );
}

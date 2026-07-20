import React from 'react';
import { motion } from 'motion/react';
import { Bot, CheckCircle2, RefreshCw } from 'lucide-react';
import { AgentEvent } from '../api';

export function LoadingState({
  title,
  description,
  agentEvents = [],
}: {
  title: string;
  description: string;
  agentEvents?: AgentEvent[];
}) {
  // Sort events by timestamp just in case
  const sortedEvents = [...agentEvents].sort((a, b) => a.timestamp - b.timestamp);

  return (
    <div className="glass-panel p-12 rounded-2xl flex flex-col items-center justify-center text-center min-h-[400px] border border-white/4 max-w-3xl mx-auto overflow-hidden relative">
      {/* Background Glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-1 bg-linear-to-r from-transparent via-accent-500/20 to-transparent"></div>

      <div className="relative mb-10 group">
        <div className="absolute inset-[-10px] bg-accent-500/15 rounded-full blur-2xl group-hover:bg-accent-500/25 transition-all duration-700"></div>
        <div className="orbital-loader relative z-10">
          <div className="orbital-ring orbital-ring-1" />
          <div className="orbital-ring orbital-ring-2" />
          <div className="orbital-ring orbital-ring-3" />
          <div className="absolute inset-0 flex items-center justify-center">
            <Bot className="w-7 h-7 text-accent-400 animate-pulse" />
          </div>
        </div>
      </div>

      <h3 className="text-2xl font-bold text-base-50 mb-3 tracking-tight">{title}</h3>
      <p className="text-base-400 text-sm max-w-md leading-relaxed mb-10">{description}</p>

      {sortedEvents.length > 0 && (
        <div className="w-full max-w-lg text-left bg-base-900/40 backdrop-blur-sm rounded-2xl p-6 border border-white/4 shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-accent-500/10"></div>

          <div className="flex items-center justify-between mb-5 px-1">
            <div className="text-[10px] font-bold text-base-500 uppercase tracking-[0.2em]">
              Neural Pipeline Status
            </div>
            <div className="flex gap-1">
              <div className="w-1.5 h-1.5 rounded-full bg-accent-500 animate-pulse"></div>
              <div className="w-1.5 h-1.5 rounded-full bg-accent-500/40"></div>
              <div className="w-1.5 h-1.5 rounded-full bg-accent-500/20"></div>
            </div>
          </div>

          <div className="space-y-4">
            {sortedEvents.map((event, i) => {
              const isLast = i === sortedEvents.length - 1;
              const isError = event.status === 'error';
              const isExplicitlyCompleted = event.status === 'completed';

              // Logic:
              // 1. If it's NOT the last event, it's considered "done" (show tick)
              // 2. If it's the last event, show spinning if it's 'working'/'started', else show tick if 'completed'
              const showTick = !isLast || isExplicitlyCompleted;
              const showLoading = isLast && !isExplicitlyCompleted && !isError;

              return (
                <motion.div
                  key={i}
                  className="flex items-start gap-4 group"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1, duration: 0.3 }}
                >
                  <div className="mt-0.5 shrink-0 relative">
                    {/* Vertical line connector */}
                    {!isLast && (
                      <div className="absolute top-5 left-1/2 -translate-x-1/2 w-px h-4 bg-white/10 group-hover:bg-accent-500/30 transition-colors"></div>
                    )}

                    {isError ? (
                      <div className="w-5 h-5 rounded-full bg-signal-error-dim flex items-center justify-center border border-signal-error/30">
                        <div className="w-2 h-2 rounded-full bg-signal-error shadow-[0_0_8px_rgba(251,113,133,0.5)]"></div>
                      </div>
                    ) : showTick ? (
                      <motion.div
                        className="flex items-center justify-center w-5 h-5 rounded-full bg-signal-success/10 border border-signal-success/20"
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 text-signal-success" />
                      </motion.div>
                    ) : (
                      <div className="relative w-5 h-5 flex items-center justify-center">
                        <RefreshCw className="w-3.5 h-3.5 text-accent-400 animate-spin" />
                        <div className="absolute inset-0 bg-accent-500/20 rounded-full blur-md animate-pulse"></div>
                      </div>
                    )}
                  </div>

                  <div className="flex-1 pb-1">
                    <p
                      className={`text-[13px] font-medium transition-colors duration-300 ${
                        isError ? 'text-signal-error' : showTick ? 'text-base-300' : 'text-base-100'
                      }`}
                    >
                      {event.message}
                    </p>
                    {showLoading && (
                      <div className="mt-2 w-full h-[2px] bg-white/5 rounded-full overflow-hidden">
                        <div className="h-full bg-accent-500 progress-bar-animated w-[40%] rounded-full"></div>
                      </div>
                    )}
                  </div>

                  <span className="text-[9px] font-mono text-base-600 mt-1 uppercase">
                    {new Date(event.timestamp * 1000).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

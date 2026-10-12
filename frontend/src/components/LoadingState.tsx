import { motion } from 'motion/react';
import { Loader2, AlertTriangle } from 'lucide-react';
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
    <div className="well border-solid min-h-[280px] w-full px-6 py-6">
      <div className="flex items-center gap-2">
        <Loader2 className="size-4 animate-spin text-accent-400" />
        <h3 className="text-heading text-base-50">{title}</h3>
      </div>
      <p className="mt-1 text-ui text-base-400">{description}</p>

      {sortedEvents.length > 0 && (
        <div className="mt-6">
          <p className="mb-2 text-xs font-medium text-base-500">Progress</p>
          <ol className="relative before:absolute before:left-[11px] before:top-3 before:bottom-3 before:w-px before:bg-line">
            {sortedEvents.map((event, i) => {
              const isLast = i === sortedEvents.length - 1;
              const isError = event.status === 'error';
              // The last event spins until it reports completed; every earlier one is done.
              const live = isLast && event.status !== 'completed' && !isError;

              return (
                <motion.li
                  key={`${event.agent_name}|${event.timestamp}|${event.message}`}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                  className={`relative flex items-baseline gap-3 rounded-lg py-1 pr-2 ${live ? 'bg-hover' : ''}`}
                >
                  <span className="relative z-10 grid w-6 shrink-0 place-items-center self-center">
                    {live
                      ? <Loader2 className="size-3.5 animate-spin text-accent-400" />
                      : <span className={`dot ${isError ? 'dot-error' : 'dot-success'}`} />}
                  </span>
                  <p className={`flex-1 text-ui ${isError ? 'text-signal-error' : 'text-base-200'}`}>
                    {isError && <><AlertTriangle className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden="true" /><span className="sr-only">Error: </span></>}
                    {event.message}
                  </p>
                  <time className="shrink-0 font-mono text-xs text-base-500 tabular-nums">
                    {new Date(event.timestamp * 1000).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                      hour12: false,
                    })}
                  </time>
                </motion.li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}

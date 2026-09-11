/**
 * Agent-event list semantics.
 *
 * Kept out of api.ts deliberately: that module reads `import.meta.env` and
 * `window` at load time, so it can only run inside the bundler. This one is
 * pure, which is what lets events.test.ts exercise it under plain `tsx`.
 */
import type { AgentEvent, Job } from './api';

/**
 * Append an event unless the same one is already in the list.
 *
 * The server replays a job's entire event history on every connect (see
 * api/routes/websocket.py) and WebSocketClient re-dials an unclean drop up to
 * five times, so a mid-run network blip would otherwise render the whole agent
 * feed a second time. Identity is (agent, message, ~timestamp): the backend
 * assigns no event ids, and float timestamps do not survive the JSON round trip
 * exactly, hence the tolerance rather than equality.
 *
 * Returns `prev` unchanged on a duplicate so React can bail out of the render.
 *
 * ponytail: O(n) scan per event. Fine at a few hundred events per job; if a
 * run ever streams thousands, key a Set on `${agent}|${message}` instead.
 */
export function appendUniqueEvent(prev: AgentEvent[], event: AgentEvent): AgentEvent[] {
  const isDupe = prev.some(
    e => e.agent_name === event.agent_name
      && e.message === event.message
      && Math.abs(e.timestamp - event.timestamp) < 0.01
  );
  return isDupe ? prev : [...prev, event];
}

/**
 * Which finished jobs are new since the last poll — the bell's notification feed.
 *
 * `seen` is mutated in place and doubles as the "have we polled yet?" flag: the
 * first call only seeds it, because jobs that were already complete when the app
 * opened are history, not news. Every later call reports genuinely fresh ones.
 */
export function collectFreshCompletions(seen: Set<string> | null, jobs: Job[]): { seen: Set<string>; fresh: Job[] } {
  const done = jobs.filter(j => j.status === 'completed');
  if (!seen) return { seen: new Set(done.map(j => j.id)), fresh: [] };
  const fresh = done.filter(j => !seen.has(j.id));
  fresh.forEach(j => seen.add(j.id));
  return { seen, fresh };
}

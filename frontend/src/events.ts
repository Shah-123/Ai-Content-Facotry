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
  if (isDupe) return prev;

  // A progress tick supersedes the one before it instead of stacking. A video
  // render emits one every 5s for a quarter of an hour, and ChatView gives
  // every event its own bubble, so appending them buried the pipeline history
  // under ~180 near-identical percentage cards. Only consecutive ticks from the
  // same agent collapse, so the distinct working steps around them survive.
  const last = prev[prev.length - 1];
  if (last
    && last.agent_name === event.agent_name
    && typeof last.metrics?.progress === 'number'
    && typeof event.metrics?.progress === 'number') {
    return [...prev.slice(0, -1), event];
  }
  return [...prev, event];
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

/**
 * Render the parallel writers' section events in section order.
 *
 * fanout() dispatches every section at once and each one announces itself when
 * it finishes, so arrival order is LLM-latency order: the feed showed
 * "Section 6/7 done" above "Section 1/7 done". Only the slots the writer events
 * occupy are re-ordered — every event keeps its own real completion timestamp,
 * and non-writer events keep their arrival position — so the feed reads 1..N
 * without inventing times or holding sections back until the whole fanout ends.
 *
 * Returns `events` unchanged when nothing moves, so React can bail out.
 */
export function orderWriterSections(events: AgentEvent[]): AgentEvent[] {
  const slots = events.flatMap(
    (e, i) => (e.agent_name === 'writer' && typeof e.metrics?.section === 'number' ? [i] : [])
  );
  const ordered = slots
    .map(i => events[i])
    .sort((a, b) => a.metrics!.section - b.metrics!.section);
  if (ordered.every((e, k) => e === events[slots[k]])) return events;

  const out = [...events];
  slots.forEach((slot, k) => { out[slot] = ordered[k]; });
  return out;
}

/** Run: npx tsx src/events.test.ts
 *  Guards the WebSocket replay de-dupe. This predicate used to be copy-pasted
 *  into four call sites in App.tsx and two of them had silently lost it, so a
 *  dropped socket mid-run rendered the whole agent feed twice. */
import assert from 'node:assert/strict';
import { appendUniqueEvent, collectFreshCompletions, orderWriterSections } from './events';
import type { AgentEvent, Job } from './api';

const ev = (agent_name: string, message: string, timestamp: number): AgentEvent =>
  ({ job_id: 'j', agent_name, status: 'working', message, timestamp });

const a = ev('research', 'Searching the web...', 1000.0);
const b = ev('writer', 'Writing section 1...', 1001.0);

// Ordinary appends accumulate.
assert.deepEqual(appendUniqueEvent(appendUniqueEvent([], a), b), [a, b]);

// The whole point: a replayed event is dropped, and the array identity is
// preserved so React bails out of the re-render.
const feed = [a, b];
assert.equal(appendUniqueEvent(feed, a), feed);
assert.equal(appendUniqueEvent(feed, b), feed);

// Timestamps do not survive the JSON round trip exactly, so near-identical
// ones are the same event...
assert.equal(appendUniqueEvent(feed, ev('research', 'Searching the web...', 1000.005)), feed);

// ...but a genuine repeat later in the run is not.
assert.equal(appendUniqueEvent(feed, ev('research', 'Searching the web...', 1060.0)).length, 3);

// Same message from a different agent is a different event.
assert.equal(appendUniqueEvent(feed, ev('qa_agent', 'Searching the web...', 1000.0)).length, 3);

// Same agent, different message, same instant is a different event.
assert.equal(appendUniqueEvent(feed, ev('research', 'Found 8 sources.', 1000.0)).length, 3);

// --- Progress ticks collapse ------------------------------------------------
const tick = (pct: number, timestamp: number): AgentEvent =>
  ({ job_id: 'j', agent_name: 'video', status: 'working',
     message: `Rendering video... ${pct}%`, timestamp, metrics: { progress: pct / 100 } });

// A run of ticks from one agent leaves a single, latest bubble — not one per tick.
const ticked = [tick(10, 2000), tick(20, 2005), tick(30, 2010)]
  .reduce(appendUniqueEvent, [a, b]);
assert.equal(ticked.length, 3);
assert.equal(ticked[2].message, 'Rendering video... 30%');

// The render's final tick renames itself to the mux stage (video.py), so the
// panel must swap the percentage line for it, not stack a second bubble.
const exported = appendUniqueEvent(ticked, { ...tick(100, 2012), message: 'Exporting video...' });
assert.equal(exported.length, ticked.length);
assert.equal(exported[exported.length - 1].message, 'Exporting video...');

// A real working step between ticks is history and must survive.
const withStep = [tick(40, 2015), ev('video', 'Compositing...', 2020), tick(50, 2025)]
  .reduce(appendUniqueEvent, ticked);
assert.deepEqual(
  withStep.slice(2).map(e => e.message),
  ['Rendering video... 40%', 'Compositing...', 'Rendering video... 50%']
);

// Ticks from a different agent do not swallow each other.
const twoAgents = appendUniqueEvent(
  withStep,
  { ...tick(60, 2030), agent_name: 'podcast_generator' }
);
assert.equal(twoAgents.length, withStep.length + 1);

// --- Bell notifications -----------------------------------------------------
const job = (id: string, status: Job['status']): Job =>
  ({ id, topic: `t-${id}`, tone: 'professional', sections: 3, status, created_at: '' });

// First poll only seeds: blogs finished before the app opened are not news.
let { seen, fresh } = collectFreshCompletions(null, [job('a', 'completed'), job('b', 'running')]);
assert.deepEqual(fresh, []);

// A job finishing after that rings the bell, exactly once.
({ seen, fresh } = collectFreshCompletions(seen, [job('a', 'completed'), job('b', 'completed')]));
assert.deepEqual(fresh.map(j => j.id), ['b']);
({ seen, fresh } = collectFreshCompletions(seen, [job('a', 'completed'), job('b', 'completed')]));
assert.deepEqual(fresh, []);

// Unfinished and failed jobs never notify.
({ fresh } = collectFreshCompletions(seen, [job('c', 'awaiting_approval'), job('d', 'failed')]));
assert.deepEqual(fresh, []);

console.log('WebSocket event de-dupe + bell notifications: all assertions passed');

// --- Parallel writer sections -----------------------------------------------
// The writers fan out, so section 6 can finish before section 1. The feed must
// still read 1..N, with every event keeping its own completion timestamp.
const sec = (n: number, timestamp: number): AgentEvent =>
  ({ job_id: 'j', agent_name: 'writer', status: 'completed',
     message: `Section ${n}/7 done`, timestamp, metrics: { section: n, total: 7 } });

const dispatch = ev('writer', 'Dispatching 7 parallel writers...', 900.0);
const merge    = ev('merger', 'Merging all sections...', 2000.0);
const jumbled  = [dispatch, sec(6, 1045), sec(1, 1047), sec(2, 1048), merge];
const fixed    = orderWriterSections(jumbled);

assert.deepEqual(fixed.map(e => e.metrics?.section ?? e.agent_name),
                 ['writer', 1, 2, 6, 'merger']);
// Timestamps travel with their own event — no invented completion times.
assert.equal(fixed[1].timestamp, 1047);
// Non-writer events never move.
assert.equal(fixed[0], dispatch);
assert.equal(fixed[4], merge);
// Already in order (and the no-writer case) returns the same array so React bails.
assert.equal(orderWriterSections(fixed), fixed);
assert.equal(orderWriterSections(feed), feed);

console.log('events.test.ts: all assertions passed');

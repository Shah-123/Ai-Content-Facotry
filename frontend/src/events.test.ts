/** Run: npx tsx src/events.test.ts
 *  Guards the WebSocket replay de-dupe. This predicate used to be copy-pasted
 *  into four call sites in App.tsx and two of them had silently lost it, so a
 *  dropped socket mid-run rendered the whole agent feed twice. */
import assert from 'node:assert/strict';
import { appendUniqueEvent } from './events';
import type { AgentEvent } from './api';

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

console.log('WebSocket event de-dupe: all assertions passed');

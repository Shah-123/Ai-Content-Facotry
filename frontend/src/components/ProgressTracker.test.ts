/** Run: npx tsx src/components/ProgressTracker.test.ts
 *  Guards the stage-rail logic — it decides what the user sees while a job runs. */
import assert from 'node:assert/strict';
import { getStageStates } from './ProgressTracker';
import type { AgentEvent } from '../api';

const ev = (agent_name: string, status: AgentEvent['status']): AgentEvent =>
  ({ job_id: 'j', agent_name, status, message: '', timestamp: 0 });

// A live job with no events yet still lights stage 0 — this is the whole
// point of rendering the rail before the topic guard returns.
assert.deepEqual(
  getStageStates([], 'pending'),
  ['active', 'pending', 'pending', 'pending', 'pending'],
);

// "Pipeline started" is a system event; it must NOT light the final stage.
assert.deepEqual(
  getStageStates([ev('system', 'started')], 'running'),
  ['active', 'pending', 'pending', 'pending', 'pending'],
);

// Real progress: research done, orchestrator working.
assert.deepEqual(
  getStageStates([ev('research', 'completed'), ev('orchestrator', 'working')], 'running'),
  ['completed', 'active', 'pending', 'pending', 'pending'],
);

// The writing path. These agent_name strings are what the backend actually
// emits; when they drifted from STAGE_MAP's keys the Write stage stayed dark
// for the whole run and nothing caught it.
assert.deepEqual(
  getStageStates([ev('research', 'completed'), ev('orchestrator', 'completed'), ev('writer', 'completed')], 'running'),
  ['completed', 'completed', 'completed', 'pending', 'pending'],
);
assert.equal(getStageStates([ev('ingest', 'working')], 'running')[0], 'active');
assert.equal(getStageStates([ev('merger', 'completed')], 'running')[2], 'completed');
assert.equal(getStageStates([ev('images', 'working')], 'running')[2], 'active');
assert.equal(getStageStates([ev('video', 'working')], 'running')[4], 'active');
assert.equal(getStageStates([ev('deepeval_evaluator', 'working')], 'running')[4], 'active');

// An errored stage surfaces as an error, not as progress.
assert.equal(getStageStates([ev('qa_agent', 'error')], 'running')[3], 'error');

// A completed job shows every stage done.
assert.deepEqual(
  getStageStates([ev('research', 'completed')], 'completed'),
  ['completed', 'completed', 'completed', 'completed', 'completed'],
);

// No job at all -> nothing lit (the component returns null in this case).
assert.deepEqual(
  getStageStates([], undefined),
  ['pending', 'pending', 'pending', 'pending', 'pending'],
);

console.log('ProgressTracker stage logic: all assertions passed');

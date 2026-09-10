/** Run: npx tsx src/components/Sidebar.test.ts
 *  Guards the Generation number fields. `min`/`max` on <input type="number">
 *  only gate form submission — they do not stop a user typing 99 or pasting
 *  text — and these two values are sent to POST /api/jobs, so the range is
 *  enforced in this function instead. */
import assert from 'node:assert/strict';
import { clampInt } from './Sidebar';

// Ordinary in-range input passes through.
assert.equal(clampInt('4', 2, 6, 3), 4);
assert.equal(clampInt('0', 0, 5, 2), 0);

// The whole point: out-of-range input is pinned to the bounds, not sent on.
assert.equal(clampInt('99', 2, 6, 3), 6);
assert.equal(clampInt('1', 2, 6, 3), 2);
assert.equal(clampInt('-4', 0, 5, 2), 0);

// Input the field cannot represent holds the previous value, so clearing the
// box mid-edit does not snap the number to the minimum under the cursor.
assert.equal(clampInt('', 2, 6, 5), 5);
assert.equal(clampInt('   ', 2, 6, 5), 5);
assert.equal(clampInt('abc', 2, 6, 5), 5);
assert.equal(clampInt('-', 0, 5, 3), 3);

// A pasted decimal lands on an integer — sections/images have no fractions.
assert.equal(clampInt('3.7', 2, 6, 3), 4);

console.log('Sidebar clampInt: all assertions passed');

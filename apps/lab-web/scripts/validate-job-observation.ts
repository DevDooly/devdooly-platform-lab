import { readFile } from 'node:fs/promises';
import { validateJobObservation } from '../src/lib/job-observation.ts';

const path = process.argv[2] || 'public/observations/jobs.latest.json';
let payload: unknown;
try { payload = JSON.parse(await readFile(path, 'utf8')); }
catch { throw new Error('Job observation file could not be parsed'); }
if (!validateJobObservation(payload)) throw new Error('Job observation public contract is invalid');
console.log(`Job observation v1 valid: ${payload.scope}, ${payload.jobs.length} jobs, captured ${payload.capturedAt}`);

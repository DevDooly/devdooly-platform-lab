import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { isObservationRecord } from '../src/lib/observation.ts';

const path = process.argv[2];
if (!path) throw new Error('Usage: npm run validate:observation -- <verified-json-path>');
const payload: unknown = JSON.parse(await readFile(resolve(path), 'utf8'));
if (!isObservationRecord(payload)) throw new Error('Observation rejected: expected verified mini-PC record, exact source SHA, balanced canonical scenario, allowed public fields and actual timestamps.');
console.log(JSON.stringify({ valid: true, schemaVersion: payload.schemaVersion, kind: payload.kind, capturedAt: payload.capturedAt, sourceCommit: payload.provenance.sourceCommit, counts: { input: payload.data.detail.inputCount, success: payload.data.detail.successCount, failure: payload.data.detail.failureCount, duplicate: payload.data.detail.duplicateCount }, scope: 'Observed API runtime; CI/CD state remains as collected.' }, null, 2));

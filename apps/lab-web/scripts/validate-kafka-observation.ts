import { open } from 'node:fs/promises';
import { MAX_KAFKA_OBSERVATION_BYTES, parseKafkaObservation } from '../src/lib/kafka-observation.ts';

const [path, option, ...extra] = process.argv.slice(2);
if (!path || extra.length || option !== undefined && option !== '--allow-isolated') {
  console.error('Usage: validate-kafka-observation.ts <path> [--allow-isolated]'); process.exit(2);
}
try {
  const file = await open(path, 'r'); const bytes = new Uint8Array(MAX_KAFKA_OBSERVATION_BYTES + 1); let size = 0;
  try {
    if (!(await file.stat()).isFile()) throw new Error('INVALID_RECORD');
    while (size < bytes.byteLength) { const result = await file.read(bytes, size, bytes.byteLength - size, null); if (!result.bytesRead) break; size += result.bytesRead; }
  } finally { await file.close(); }
  if (size > MAX_KAFKA_OBSERVATION_BYTES) throw new Error('INVALID_RECORD');
  const record = parseKafkaObservation(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes.subarray(0, size)));
  if (!record || option !== '--allow-isolated' && record.environment !== 'MINI_PC') throw new Error('INVALID_RECORD');
  console.log(JSON.stringify({ valid: true, kind: record.kind, environment: record.environment, scope: record.scope,
    sourceCommit: record.sourceCommit, captureStartedAt: record.captureStartedAt, capturedAt: record.capturedAt, commitState: record.commitState, lag: record.lag }));
} catch { console.error('INVALID_KAFKA_OBSERVATION'); process.exitCode = 1; }

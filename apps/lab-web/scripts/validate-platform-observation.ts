import { readFile } from 'node:fs/promises';
import { MAX_PLATFORM_OBSERVATION_BYTES, validatePlatformObservation } from '../src/lib/platform-observation.ts';

const file = process.argv[2];
if (!file) {
  console.error('Usage: node --experimental-strip-types scripts/validate-platform-observation.ts <file>');
  process.exitCode = 2;
} else {
  try {
    const text = await readFile(file, 'utf8');
    if (Buffer.byteLength(text, 'utf8') > MAX_PLATFORM_OBSERVATION_BYTES || !validatePlatformObservation(JSON.parse(text))) throw new Error('invalid');
    console.log('Platform observation: valid public record');
  } catch {
    // Never print the supplied body, path, parser error or a raw collector error.
    console.error('Platform observation: rejected');
    process.exitCode = 1;
  }
}

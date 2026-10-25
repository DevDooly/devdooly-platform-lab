import { isRunDetail } from './api.ts';
import type { RunDetail } from './api.ts';
import type { ApiReadResult } from '../data/public-api-reference.ts';

export type ApiRunResult = { kind: 'valid'; detail: RunDetail } | { kind: 'invalid' | 'id-mismatch' };

/** Validate the stored detail response and its request identity, not current service health. */
export function parseApiRunResult(result: Pick<ApiReadResult, 'path' | 'json'>): ApiRunResult {
  const match = /^\/demo\/runs\/([a-z0-9][a-z0-9._-]{0,79})$/.exec(result.path);
  if (!match || match[0] !== result.path) return { kind: 'invalid' };

  let detail: unknown;
  try { detail = JSON.parse(result.json); }
  catch { return { kind: 'invalid' }; }
  if (!detail || typeof detail !== 'object' || Array.isArray(detail) || !isRunDetail(detail)) {
    return { kind: 'invalid' };
  }
  return detail.id === match[1] ? { kind: 'valid', detail } : { kind: 'id-mismatch' };
}

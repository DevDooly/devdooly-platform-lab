import { isRun } from './api.ts';
import type { Run } from './api.ts';
import { apiEndpointPath } from '../data/public-api-reference.ts';

export interface ApiRunChoices {
  items: Run[];
  observedAt: string;
}

/** Project a raw API response into optional choices without changing its HTTP/JSON result. */
export function parseApiRunChoices(json: string): ApiRunChoices | null {
  let value: unknown;
  try { value = JSON.parse(json); }
  catch { return null; }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const payload = value as Record<string, unknown>;
  if (!Array.isArray(payload.items) || typeof payload.observedAt !== 'string'
    || Number.isNaN(Date.parse(payload.observedAt))) return null;

  const ids = new Set<string>();
  for (const item of payload.items) {
    if (!isRun(item) || apiEndpointPath('detail', item.id) === null || ids.has(item.id)) return null;
    ids.add(item.id);
  }
  return { items: payload.items, observedAt: payload.observedAt };
}

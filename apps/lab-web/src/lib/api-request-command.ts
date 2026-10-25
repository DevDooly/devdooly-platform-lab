import { apiEndpointPath } from '../data/public-api-reference.ts';
import type { ApiEndpointId } from '../data/public-api-reference.ts';
import { publicApiConfiguration, publicReadUrl } from './public-api-base.ts';

/** Only characters needed by the configured HTTPS origins and fixed public paths. */
function asciiUrl(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && !/[^A-Za-z0-9._~:/-]/.test(value);
}

/** Produce one explicit GET command for the current selection; never execute it or infer response health. */
export function buildApiRequestCommand(
  apiBase: string,
  endpointId: ApiEndpointId,
  runId: string,
  shell: 'posix' | 'powershell',
  siteOrigin?: string,
): string | null {
  if ((shell !== 'posix' && shell !== 'powershell') || !asciiUrl(apiBase) || typeof runId !== 'string') return null;
  const path = apiEndpointPath(endpointId, runId);
  if (!path || !asciiUrl(path)) return null;

  let configuration = publicApiConfiguration(apiBase);
  if (configuration.invalid) return null;
  if (!configuration.externalHttps) {
    if (!asciiUrl(siteOrigin)) return null;
    try {
      const origin = new URL(siteOrigin);
      if (origin.protocol !== 'https:' || origin.origin !== siteOrigin) return null;
    } catch { return null; }
    configuration = publicApiConfiguration(`${siteOrigin}/api`);
  }
  if (configuration.invalid || !configuration.externalHttps) return null;
  const url = publicReadUrl(configuration.apiBase, path);
  if (!asciiUrl(url) || !url.startsWith('https://')) return null;

  const executable = shell === 'powershell' ? 'curl.exe' : 'curl';
  return `${executable} -q --request GET --header 'Accept: application/json' --connect-timeout 5 --max-time 8 --silent --show-error --fail --url '${url}'`;
}

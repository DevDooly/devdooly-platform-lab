/** One explicit HTTPS base for the six public GET routes; no browser credentials. */
export interface PublicApiConfiguration { apiBase: string; externalHttps: boolean; invalid: boolean; }
export function publicApiConfiguration(value?: string): PublicApiConfiguration {
  if (value === undefined || value === '' || value === '/api' || value === '/api/') {
    return { apiBase: '/api', externalHttps: false, invalid: false };
  }
  const invalid = { apiBase: 'invalid-public-api-base', externalHttps: false, invalid: true };
  if (value.length > 2048 || value !== value.trim() || /[@?#]/.test(value)) return invalid;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash
      || !/^\/(?:api|platform-lab\/api)\/?$/.test(url.pathname) || url.port
      || !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/.test(url.hostname)
      || /^[0-9.]+$/.test(url.hostname) || /\.(?:local|localhost|internal|svc)$/.test(url.hostname)) return invalid;
    return { apiBase: `${url.origin}${url.pathname.replace(/\/$/, '')}`, externalHttps: true, invalid: false };
  } catch { return invalid; }
}

const exactPaths = new Set(['/platform/summary', '/platform/releases', '/demo/runs',
  '/jobs/observation', '/kafka/observation']);
export function isPublicReadPath(path: string): boolean {
  return exactPaths.has(path) || /^\/demo\/runs\/[a-z0-9][a-z0-9._-]{0,79}$/.test(path);
}
export function publicReadUrl(base: string, path: string): string | null {
  if (!isPublicReadPath(path)) return null;
  const configuration = publicApiConfiguration(base);
  return configuration.invalid ? null : `${configuration.apiBase}${path}`;
}

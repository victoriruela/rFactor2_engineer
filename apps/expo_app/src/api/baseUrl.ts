function trimTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, '');
}

function ensureApiSuffix(value: string): string {
  const normalized = trimTrailingSlashes(value);
  if (normalized.endsWith('/api')) {
    return normalized;
  }
  return `${normalized}/api`;
}

export interface ResolveApiBaseUrlInput {
  envApiUrl?: string;
  isWeb?: boolean;
  windowOrigin?: string;
}

export function resolveApiBaseUrl(input: ResolveApiBaseUrlInput = {}): string {
  const envApiUrl = input.envApiUrl?.trim();

  if (envApiUrl) {
    return ensureApiSuffix(envApiUrl);
  }

  if (input.isWeb && input.windowOrigin) {
    // In production the Go backend serves the frontend from the same origin.
    // In development the Expo bundler runs on a different port (8081, 8082…)
    // than the Go backend (8080), so same-origin /api would point at the
    // bundler instead of the backend. Only use origin-based resolution when
    // the origin is NOT a local non-backend address.
    try {
      const url = new URL(input.windowOrigin);
      const isLocalDevPort =
        (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
        url.port !== '' &&
        url.port !== '8080';
      if (!isLocalDevPort) {
        return `${trimTrailingSlashes(input.windowOrigin)}/api`;
      }
    } catch {
      return `${trimTrailingSlashes(input.windowOrigin)}/api`;
    }
  }

  return 'http://localhost:8080/api';
}

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
    return `${trimTrailingSlashes(input.windowOrigin)}/api`;
  }

  return 'http://localhost:8080/api';
}

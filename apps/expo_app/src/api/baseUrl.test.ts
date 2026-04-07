import { resolveApiBaseUrl } from './baseUrl';

describe('resolveApiBaseUrl', () => {
  it('uses env URL and appends /api if needed', () => {
    expect(resolveApiBaseUrl({ envApiUrl: 'https://car-setup.com' })).toBe('https://car-setup.com/api');
  });

  it('keeps env URL when it already contains /api', () => {
    expect(resolveApiBaseUrl({ envApiUrl: 'https://car-setup.com/api' })).toBe('https://car-setup.com/api');
  });

  it('uses same-origin /api in web when env is unset', () => {
    expect(
      resolveApiBaseUrl({
        isWeb: true,
        windowOrigin: 'https://car-setup.com',
      }),
    ).toBe('https://car-setup.com/api');
  });

  it('falls back to localhost only when no env and no web origin are available', () => {
    expect(resolveApiBaseUrl({ isWeb: false })).toBe('http://localhost:8080/api');
  });
});

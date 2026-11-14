/**
 * API keys (the client's and the administrator's), remembered in localStorage between visits.
 *
 * Storage can be unavailable (private mode, blocked site data) and then throws: the app keeps
 * working and only forgets the key.
 */

export const CLIENT_KEY_ITEM = "giunti.apiKey";
export const ADMIN_KEY_ITEM = "giunti.adminKey";

export function loadKey(item: string): string | null {
  try {
    return window.localStorage.getItem(item);
  } catch {
    return null;
  }
}

export function saveKey(item: string, key: string): void {
  try {
    window.localStorage.setItem(item, key);
  } catch {
    // Not persisted: the key is still used for this visit.
  }
}

export function forgetKey(item: string): void {
  try {
    window.localStorage.removeItem(item);
  } catch {
    // Nothing stored or storage blocked: nothing to remove.
  }
}

export function loadApiKey(): string | null {
  return loadKey(CLIENT_KEY_ITEM);
}

export function saveApiKey(apiKey: string): void {
  saveKey(CLIENT_KEY_ITEM, apiKey);
}

export function forgetApiKey(): void {
  forgetKey(CLIENT_KEY_ITEM);
}

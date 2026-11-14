/**
 * Invitation links: `https://…/#clave=gk_…` signs the person in with one click.
 *
 * The key travels in the URL fragment, which browsers never send to the server, and is removed
 * from the address bar as soon as it is read so it does not stay in the history or get shared.
 */

const FRAGMENT_PARAMETER = "clave";

export function takeKeyFromUrl(): string | null {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const key = fragment.get(FRAGMENT_PARAMETER)?.trim();
  if (!key) {
    return null;
  }
  const { pathname, search } = window.location;
  window.history.replaceState(window.history.state, "", `${pathname}${search}`);
  return key;
}

/**
 * Where somebody may be sent after signing in.
 *
 * A sign-in page that redirects to whatever `?next=` says is a way to make a
 * link to this site land somewhere else. So the choice is from a list written
 * here, and anything not on it is the default.
 */
const AFTER_SIGN_IN = new Set(["/play", "/write"]);

export function nextStep(requested: string | string[] | undefined): string {
  const value = Array.isArray(requested) ? requested[0] : requested;
  return value && AFTER_SIGN_IN.has(value) ? value : "/play";
}

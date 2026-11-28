/**
 * Where somebody may be sent after signing in.
 *
 * A sign-in page that redirects to whatever `?next=` says is a way to make a
 * link to this site land somewhere else. So the choice is from a list written
 * here, and anything not on it is the default.
 */
const AFTER_SIGN_IN = new Set(["/play", "/write"]);

/** The game opened on one question, as a question's "Make a forecast" asks: its address only. */
const PLAY_QUESTION = /^\/play\?question=[a-z0-9]+(-[a-z0-9]+)*$/;

export function nextStep(requested: string | string[] | undefined): string {
  const value = Array.isArray(requested) ? requested[0] : requested;
  if (!value) return "/play";
  if (AFTER_SIGN_IN.has(value)) return value;
  return value.length <= 220 && PLAY_QUESTION.test(value) ? value : "/play";
}

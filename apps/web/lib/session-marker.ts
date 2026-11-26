/**
 * A second cookie that says one thing: "signed in".
 *
 * The session itself lives in a cookie scripts cannot read, which is right,
 * and which also means a page cannot tell from the browser whether to offer
 * "Sign in" or "Play". Asking the server would work — and would mean every
 * public page is rendered afresh for every visitor instead of once for
 * everybody, for the sake of one link in the header.
 *
 * So the server sets this beside the real cookie and clears it with it. It
 * holds no secret and grants nothing: change it by hand and the worst that
 * happens is the wrong link is shown, and the server corrects you one click
 * later.
 */
export const SIGNED_IN_COOKIE = "signed_in";

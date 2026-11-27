// Wakes the game's API before the site is built, when there is one to wake.
//
// Some pages are built from the API's figures: the list of what moved, the
// list of questions, the sitemap. On a host that rests an idle server, the
// API is usually asleep when a deploy starts, and a build that cannot reach
// it builds those pages saying so — true, but a poor first hour for a new
// deployment. So the build knocks first and waits, up to two minutes, for
// the figures to be ready.
//
// It never fails the build. With no API configured it returns at once; if the
// API does not answer in time the site is built without it, as before, and
// fills those pages in on the first visit after the API is back.

const base = (process.env.API_BASE_URL ?? "").trim().replace(/\/+$/, "");
const WAIT_MS = 120_000;
const PAUSE_MS = 4_000;

if (base) {
  const deadline = Date.now() + WAIT_MS;
  let said = false;
  let ready = false;

  while (!ready && Date.now() < deadline) {
    try {
      // The route the pages themselves read. 200: the figures are current.
      // 404: an API from before this route existed — awake, and there is
      // nothing more to wait for. Anything else, 503 included: not yet.
      const response = await fetch(`${base}/v1/questions/moves?limit=1`, {
        signal: AbortSignal.timeout(15_000),
      });
      ready = response.ok || response.status === 404;
    } catch {
      // Not answering yet. Asking is what wakes it.
    }
    if (!ready) {
      if (!said) console.log("Waiting for the API to wake and read its figures…");
      said = true;
      await new Promise((resolve) => setTimeout(resolve, PAUSE_MS));
    }
  }

  console.log(
    ready
      ? "The API is awake."
      : "The API did not answer in time. Building without its figures; the pages fill in later.",
  );
}

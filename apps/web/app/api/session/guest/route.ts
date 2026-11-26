import { callApi, sessionResponse } from "@/lib/server/upstream";

/** Start playing without an account. */
export async function POST() {
  return sessionResponse(await callApi("/v1/auth/guest", { method: "POST" }));
}

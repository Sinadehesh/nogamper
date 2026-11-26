import {
  badRequest,
  callApi,
  currentToken,
  readJson,
  sessionResponse,
} from "@/lib/server/upstream";

/**
 * Create an account — or, for somebody already playing as a guest, give that
 * same account an email and a password.
 *
 * The API tells the two apart by whether a guest's session comes with the
 * request, so the cookie is forwarded if there is one. It is forwarded as a
 * hint, not a requirement: a cookie that has lapsed is treated as nobody, and
 * the sign-up goes ahead as a new account.
 */
export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body) return badRequest();

  const token = await currentToken();

  return sessionResponse(
    await callApi("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: body.email,
        password: body.password,
        display_name: body.display_name,
      }),
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    }),
  );
}

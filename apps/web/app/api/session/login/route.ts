import { badRequest, callApi, readJson, sessionResponse } from "@/lib/server/upstream";

export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body) return badRequest();

  return sessionResponse(
    await callApi("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: body.email, password: body.password }),
    }),
  );
}

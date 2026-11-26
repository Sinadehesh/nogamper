import { NextResponse } from "next/server";

import { SESSION_COOKIE, callApi } from "@/lib/server/upstream";
import type { UserProfile } from "@/lib/types";

type SessionResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  is_new_user: boolean;
  user: UserProfile;
};

export async function POST(request: Request) {
  let initData: unknown;
  try {
    ({ initData } = await request.json());
  } catch {
    return NextResponse.json(
      { code: "bad_request", detail: "Expected a JSON body." },
      { status: 400 },
    );
  }

  if (typeof initData !== "string" || initData.length === 0) {
    return NextResponse.json(
      { code: "bad_request", detail: "initData is required." },
      { status: 400 },
    );
  }

  const result = await callApi<SessionResponse>("/v1/auth/session", {
    method: "POST",
    body: JSON.stringify({ initData }),
  });

  if (!result.ok) {
    return NextResponse.json(result.error, { status: result.status });
  }

  const { access_token, expires_at, is_new_user, user } = result.data;
  const response = NextResponse.json({ isNewUser: is_new_user, user });

  const secure = process.env.NODE_ENV === "production";
  response.cookies.set({
    name: SESSION_COOKIE,
    value: access_token,
    httpOnly: true,
    secure,
    sameSite: secure ? "none" : "lax",
    path: "/",
    expires: new Date(expires_at),
  });

  return response;
}

export async function DELETE() {
  const result = await callApi<null>("/v1/auth/session", {
    method: "DELETE",
    authenticated: true,
  });

  const response = result.ok
    ? new NextResponse(null, { status: 204 })
    : NextResponse.json(result.error, { status: result.status });

  response.cookies.delete(SESSION_COOKIE);
  return response;
}

import { NextRequest } from "next/server";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context) {
  const apiBase = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8010";
  const apiToken = process.env.CATALOGO_API_TOKEN;
  if (!apiToken) {
    return Response.json(
      { detail: "Proxy não configurado: CATALOGO_API_TOKEN ausente" },
      { status: 503 },
    );
  }

  const { path } = await context.params;
  const destino = new URL(path.map(encodeURIComponent).join("/"), `${apiBase}/`);
  destino.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.set("authorization", `Bearer ${apiToken}`);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();
  const resposta = await fetch(destino, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  });

  const responseHeaders = new Headers(resposta.headers);
  responseHeaders.delete("connection");
  responseHeaders.delete("transfer-encoding");
  return new Response(resposta.body, {
    status: resposta.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;

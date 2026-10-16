import { NextResponse } from "next/server";

export async function POST(req: Request) {
  const base = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";
  const body = await req.json();

  let r: Response;
  try {
    r = await fetch(`${base}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return NextResponse.json({ detail: "TTS backend unavailable" }, { status: 503 });
  }

  const buf = await r.arrayBuffer();

  if (!r.ok) {
    try {
      const txt = Buffer.from(buf).toString("utf8");
      const json = JSON.parse(txt);
      return NextResponse.json(json, { status: r.status });
    } catch {
      return NextResponse.json({ detail: "TTS error" }, { status: r.status });
    }
  }

  const res = new NextResponse(buf, { status: r.status });

  const ct = r.headers.get("content-type");
  if (ct) res.headers.set("content-type", ct);
  const latency = r.headers.get("x-latency-ms");
  if (latency) res.headers.set("x-latency-ms", latency);
  const model = r.headers.get("x-model");
  if (model) res.headers.set("x-model", model);

  return res;
}

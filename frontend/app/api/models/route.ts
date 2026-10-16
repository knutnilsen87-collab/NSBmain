import { NextResponse } from "next/server";

export async function GET() {
  const base = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";

  try {
    const r = await fetch(`${base}/models`, { cache: "no-store" });
    const data = await r.json();
    return NextResponse.json(data, { status: r.status });
  } catch {
    return NextResponse.json({ models: [] }, { status: 503 });
  }
}

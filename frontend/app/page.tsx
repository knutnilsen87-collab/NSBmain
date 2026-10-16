"use client";

import { useEffect, useMemo, useState } from "react";

export default function Page() {
  const [text, setText] = useState("Hei! Dette er en test av norsk tale.");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("latest");
  const [busy, setBusy] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");

  const canPlay = useMemo(() => !!audioUrl, [audioUrl]);

  async function refreshModels() {
    try {
      const res = await fetch("/api/models");
      const data = await res.json();
      setModels(data.models ?? []);
    } catch {
      setModels([]);
    }
  }

  useEffect(() => {
    refreshModels();
    const id = setInterval(refreshModels, 5000);
    return () => clearInterval(id);
  }, []);

  async function generate() {
    setBusy(true);
    setStatus("");
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);

    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, model, format: "wav", speed: 1.0 }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setStatus(`Feil: ${res.status} ${err?.detail ?? ""}`.trim());
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);

      const latency = res.headers.get("x-latency-ms");
      const usedModel = res.headers.get("x-model");
      setStatus(`OK - model=${usedModel ?? model} - ${latency ?? "?"}ms`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 900, margin: "40px auto", padding: 16 }}>
      <h1 style={{ fontSize: 28 }}>NorwegianSpeechBase - TTS</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <label>Model:</label>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          <option value="latest">latest</option>
          {models.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <button onClick={refreshModels}>Refresh</button>
        <span style={{ opacity: 0.7 }}>Legg checkpoints i <code>backend/models/</code></span>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        style={{ width: "100%", padding: 12 }}
      />

      <div style={{ marginTop: 12, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button onClick={generate} disabled={busy || !text.trim()}>
          {busy ? "Generating..." : "Generate"}
        </button>
        <span>{status}</span>
      </div>

      <div style={{ marginTop: 16 }}>
        {canPlay ? <audio controls src={audioUrl ?? undefined} style={{ width: "100%" }} /> : null}
      </div>
    </main>
  );
}

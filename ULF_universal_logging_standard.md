# Universal verdensklasse-loggstandard (ULF v1)

Denne standarden er **språk‑uavhengig** og kan brukes likt i frontend, backend, batch‑jobber, microservices og infrastruktur.

**Mål:**  
- Gjøre feil krystallklare  
- Gjøre feil 100 % reproduserbare  
- Redusere sannsynlighet for at samme feil skjer mer enn én gang  

**Prinsipp:**  
➡️ Én strukturert JSON‑logglinje per hendelse (JSONL)

---

## 1. Kjerneprinsipper

1. Strukturert JSON – aldri fritekst  
2. Samme felter i alle språk og systemer  
3. Full kontekst + kausalitet + bevis  
4. Ingen PII eller secrets – kun redigert data + fingerprint  
5. Alle ERROR‑logger skal kunne reproduseres  

---

## 2. Obligatoriske toppfelt (ALLTID)

```json
{
  "v": "ulf-1.0",
  "ts": "2026-01-03T12:34:56.789Z",
  "level": "INFO",
  "msg": "Kort, menneskelig oppsummering",
  "event": { "type": "http.request", "name": "CreateOrder", "stage": "start" },
  "service": { "name": "api", "version": "1.18.2", "build_sha": "abc123", "runtime": "node-20" },
  "env": { "name": "prod", "region": "eu-north-1", "cluster": "k8s-prod-1" },
  "ids": {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "parent_span_id": "b9c7c989f97918e1",
    "request_id": "req_01H...",
    "correlation_id": "checkout_90210",
    "session_id": "sess_...",
    "tenant_id": "tnt_123",
    "user_id": "usr_hash_5f2a..."
  }
}
```

---

## 3. Error‑objekt (OBLIGATORISK)

```json
"error": {
  "kind": "TimeoutError",
  "message": "Payment authorization timed out",
  "stacktrace": "full stacktrace",
  "code": "ORD-5001",
  "fingerprint": "fp:2a8c0e...",
  "handled": false
}
```

---

## 4. Reproduksjon (kun ved ERROR)

```json
"repro": {
  "steps": [
    "Replay request req_01H...",
    "Mock payments latency to 6s"
  ],
  "seed": 482019,
  "expected": "201 Created",
  "actual": "500 ORD-5001"
}
```

---

## 5. Fingerprint‑regel

Samme bug = samme fingerprint  
Ny fingerprint = ny bug  

---

**ULF v1 – møt hver bug én gang.**

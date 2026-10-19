"""Kontroll av talemotorens lagring uten å starte tjenesten.

    python -m nsb_engine.admin verify          # er innsynsloggen uendret?
    python -m nsb_engine.admin sessions        # lagrede økter (uten innhold)
    python -m nsb_engine.admin purge           # slett utløpte økter nå
    python -m nsb_engine.admin delete <id>     # slett én økt
    python -m nsb_engine.admin log [--session <id>]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from nsb_engine.security import AuditLog, MasterKey, Paths, Vault, default_root
from nsb_engine.sessions import SessionStore


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", help="standard: brukerens AppData")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify")
    sub.add_parser("sessions")
    sub.add_parser("purge")
    d = sub.add_parser("delete")
    d.add_argument("session")
    lg = sub.add_parser("log")
    lg.add_argument("--session")
    args = ap.parse_args(argv)

    paths = Paths(Path(args.data_dir) if args.data_dir else default_root()).ensure()
    master = MasterKey(paths)
    audit = AuditLog(paths, master)
    store = SessionStore(paths, Vault(paths, master), audit)
    if args.cmd == "verify":
        ok, line = audit.verify()
        n = len(audit.entries())
        print(f"Innsynsloggen er uendret ({n} linjer)." if ok else f"Innsynsloggen er endret eller skadet fra linje {line}.")
        return 0 if ok else 2
    if args.cmd == "sessions":
        for m in store.list():
            print(json.dumps(asdict(m), ensure_ascii=False))
        return 0
    if args.cmd == "purge":
        removed = store.purge_expired()
        print(f"Slettet {len(removed)} utløpte økter.")
        return 0
    if args.cmd == "delete":
        try:
            store.meta(args.session)
        except KeyError:
            print("Ukjent økt.")
            return 1
        store.delete(args.session, actor="admin", reason="admin")
        print("Slettet.")
        return 0
    for e in audit.entries(args.session):
        print(json.dumps(e, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Sikkerhet

## Hendelse: privat nøkkel i offentlig git-historikk (lukket 2026-10-16)

| Punkt | Status |
| --- | --- |
| Hva | RSA-nøkkelen `security/keys/private_key.xml` lå i den offentlige historikken til `knutnilsen87-collab/NSBmain` fra første commit (desember 2025) |
| Bruk | Bare lokal signering av loggfiler (`FBL_TrainAudioEncoder.ps1`, `scripts/fbl_logging.ps1`). Ingen ekstern tjeneste, token eller kryptering brukte nøkkelen |
| Historikk | Skrevet om 2026-10-16: `main` og `archive/scaffold-2026-05` er nye historikker uten nøkkelen, torrent-filer eller loggdata |
| Rotasjon | Nytt nøkkelpar laget 2026-10-16 med `scripts/rotate_signing_key.ps1`. Den lekkede nøkkelen er identifisert ved sha256 av RSA-modulus, `09f3fb20…2b680149`, i [revoked_keys.json](revoked_keys.json); skriptet nekter å bruke den og skriver `security/pubkeys/REVOKED.json` lokalt |
| Gamle signaturer | Alle `.sig`-filer laget før 2026-10-16 regnes som ugyldige |
| Gjenstår | GitHub kan i en periode vise gamle commits via direkte SHA-lenke. Be GitHub Support fjerne bufrede visninger om nødvendig. Slett gamle lokale kloner |

## Regler

- Private nøkler, `.env`-filer og signaturer committes aldri. `.gitignore` stopper `security/keys/`, `*.key`, `*private*` og `.env*`.
- Lydopptak av personer (også testopptak) committes ikke. `*.wav`, `*.flac` og `*.mp3` er ignorert; unntaket er `apps/pilot-asr-api/smoke_test.wav`, som er syntetisk.
- Treningsdata brukes bare med dokumentert lisens; se [DATA_REGISTER.md](DATA_REGISTER.md).
- Kjør `gitleaks git . --log-opts="--all" --redact` før større push.

import os, csv, argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wavs_dir', required=True)
    ap.add_argument('--metadata_csv', required=True)
    args = ap.parse_args()

    wavs_dir = args.wavs_dir
    meta = args.metadata_csv

    if not os.path.isdir(wavs_dir):
        raise SystemExit(f'No such wavs_dir: {wavs_dir}')
    if not os.path.isfile(meta):
        raise SystemExit(f'No such metadata_csv: {meta}')

    missing = 0
    total = 0
    empty_text = 0

    with open(meta, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            total += 1
            parts = line.split('|', 1)
            if len(parts) != 2:
                raise SystemExit(f'Bad line (expected wav|text): {line}')
            fn, text = parts[0].strip(), parts[1].strip()
            if not text:
                empty_text += 1
            p = os.path.join(wavs_dir, fn)
            if not os.path.isfile(p):
                missing += 1

    print('=== DATASET VALIDATION ===')
    print('Total entries:', total)
    print('Missing wavs:', missing)
    print('Empty texts:', empty_text)
    if total == 0:
        raise SystemExit('No usable entries in metadata.csv')
    if missing > 0:
        raise SystemExit('Fix missing wav files before training.')
    print('OK: Dataset structure looks good.')

if __name__ == '__main__':
    main()

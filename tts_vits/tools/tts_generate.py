# MVP CLI stub: later this should load a trained VITS and generate WAV.
# For now, it validates config + normalizes text + prints next steps.

import argparse, yaml
from src.text_normalizer_no import normalize_no
from src.tokenizer_no import CharTokenizer

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--text', required=True)
    ap.add_argument('--voice_ref_wav', required=False, default=None, help='Optional: reference wav for speaker embedding later')
    ap.add_argument('--out', required=False, default='out.wav')
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, 'r', encoding='utf-8'))
    t = normalize_no(args.text)
    tok = CharTokenizer()
    ids = tok.encode(t)

    print('[OK] Loaded config:', args.config)
    print('[OK] Normalized text:', t)
    print('[OK] Token count:', len(ids))
    print('\\nNEXT:')
    print(' - Implement VITS training (paired wav+text).')
    print(' - Add speaker embedding extraction using scripts/infer_audio_encoder.py (or an integrated function).')
    print(' - Replace stub with real model inference + vocoder output.')

if __name__ == '__main__':
    main()

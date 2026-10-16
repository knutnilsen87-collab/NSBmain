# Locked Eval Policy

## Regel
Locked eval-datasett skal aldri brukes i trening, finetuning eller weak supervision.

## Required splits
- train
- dev
- locked_eval
- production_shadow_eval

## Promotion gate
En modell kan bare promoteres når:
- samme locked eval brukes for baseline og kandidat
- comparison report finnes
- kandidat viser målbar forbedring
- deploy record og rollback path finnes

## Forbudt
- manuell cherry-picking av eval-filer
- blanding av train og eval
- promotering basert kun på subjektive tester

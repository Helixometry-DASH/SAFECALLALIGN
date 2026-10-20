# SAFECALLALIGN

A multilingual, intervention-timed fraud-speech dataset and protective-alignment
benchmark for Audio-LMs. Calls are generated natively per language, labeled on six
axes, and paired as **near-domain divergence-point siblings** (a fraud call and a
lawful call sharing an identical prefix, splitting at the malicious turn) so the data
supports not just fraud *detection* but *when and how to intervene*.

## Status
- **Stage 0 — Taxonomy: finalized.** 39 fraud types (+2 subtypes), 4 super-categories,
  6 labeling axes, grounded in 8 national authorities + global sources. See
  [`docs/taxonomy.md`](docs/taxonomy.md).
- Stages 1–8 (profiling → two-agent generation → divergence siblings → QC →
  labeling/timing → prosody TTS → freeze → alignment layer): pending.

## Languages (10)
English, Chinese, Korean, Hindi, Indonesian, Spanish, Vietnamese, Portuguese-BR,
+ code-switch Hinglish (hi-en) and Konglish (ko-en).

## Layout
```
configs/   languages.yaml, taxonomy.yaml
docs/      taxonomy.md
src/       safecallalign/ (pipeline modules — pending)
scripts/   stage entry points (pending)
tests/
```

## Disclaimer on named entities
For realism, dialogues reference **real organisation names** (banks, agencies, couriers, apps,
platforms) and native currency, because scammers impersonate real institutions. **These names
appear only as the entities that fraudsters *impersonate*; no wrongdoing, affiliation, or
endorsement by any named organisation is implied.** No real working phone numbers, URLs, links,
or account numbers are included — those are always placeholders. See `configs/entities.yaml`.

## Relation to prior work
Builds on the TeleAntiFraud taxonomy but extends it from Chinese detection to a
multilingual, mechanism-annotated, intervention-timed setting (~5–6× the fraud-type
coverage, 8 base languages + 2 code-switch).

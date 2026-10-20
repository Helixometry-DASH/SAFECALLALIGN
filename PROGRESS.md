# SAFECALLALIGN — Progress Log

_Multilingual, intervention-timed fraud-speech dataset + protective-alignment benchmark._
_Last updated: 2026-10-20._

## Pipeline status (8 stages)

| Stage | What it produces | Status |
|---|---|---|
| **0. Taxonomy** | 39 fraud types (+2 subtypes), 4 super-categories, 6 labeling axes | ✅ done (committed) |
| **1. Profiles** | grounded scenario blueprints (per fraud_type × language) | ✅ 20,000 generated; QC done; **converging to 2,000 clean/lang** |
| 2. Two-agent dialogues | fraud + near-domain benign **divergence siblings** | ⏳ next (generator to build) |
| 3. Divergence siblings | fork each call at the `risk_node` (shared prefix) | ⏳ |
| 4. Dialogue QC | realism-judge + dedup | ⏳ |
| 5. Labels + timing | per-turn labels, T_s/T_c/T_h | ⏳ |
| 6. Prosody TTS | role/emotion audio | ⏳ |
| 7. Freeze + provenance | snapshot manifests | ⏳ |
| 8. Alignment layer | prefixes + stage-aware preference pairs | ⏳ |

## Languages (10)
Monolingual: en, zh, ko, hi, id, es, vi, pt-BR. Code-switch: hi-en (Hinglish), ko-en (Konglish).
Native generation per language; native currency + real entities.

## Taxonomy (Stage 0) — `configs/taxonomy.yaml`, `docs/taxonomy.md`
39 fraud types across impersonation / investment-lure / credential-compromise / coercion-threat,
grounded in 8 national authorities (FBI IC3/FTC, I4C/NCRP, FSS/KNPA, OJK/Satgas PASTI, INCIBE,
Bộ Công an, Febraban, MPS China) + global (ACCC/GSMA/USCIS). 6 axes: fraud_type, impersonated_entity,
manipulation_tactics (9, Cialdini+fear), requested_action, compliance_level, channel.

## Profiles (Stage 1)
- **20,000 generated** (2,000 × 10 languages), real impersonated entities + native currency.
- Seeds: per-language **real-case** abstracts with source URLs (`configs/seeds/<lang>.jsonl`) +
  advisory-cited **generic** per-type seeds (`configs/seeds/_generic.jsonl`).
- Entities + currency: `configs/entities.yaml`. Schema: `configs/profile_schema.yaml`.
- **QC (72B judge + near-dup) pass-rate ~0.95** (per lang 0.91–0.99; id/vi best, en/hi lowest).
  Flagged ~5% removed; pipeline converges each language back to 2,000 clean.

### QC pass-rates (first full pass)
| lang | pass | | lang | pass |
|---|--:|---|---|--:|
| id | 0.987 | | pt | 0.966 |
| vi | 0.983 | | ko | 0.958 |
| zh | 0.969 | | hi-en | 0.958 |
| es | 0.968 | | hi | 0.929 |
| ko-en | 0.966 | | en | 0.914 |

## Infra notes
- Generator/judge model: **Qwen2.5-72B-Instruct-AWQ** (vLLM), 1× A100/H100 (needs ~40 GB+; MIG 40 GB too small).
- Runs are **resume-safe** (checkpoint per round) and launched as **self-contained sbatch** jobs
  (`/users/msingh/GPU/scalign_pipeline.sh`) so work runs on allocation without a live session.
- Env gotcha: pin `setuptools==75.8.0` in the `fraudgen` env (newer setuptools breaks torch/vLLM).
- See [SETUP.md](SETUP.md) to run on another server.

## Known issues / next
- Finish Stage-1 convergence to exactly 2,000 clean/lang (top-up ↔ QC loop; GPU-queued).
- Build Stage-2 two-agent generator + a short dialogue set for human validation before full run.
- Base plan: 20k profiles → ~40k dialogues (20k fraud + 20k benign siblings).

# SAFECALLALIGN — Setup on another server

How to stand up the pipeline on a new machine/cluster and continue the work.

## 1. Clone
```bash
git clone git@github.com:Helixometry-DASH/SAFECALLALIGN.git
cd SAFECALLALIGN
```

## 2. Python env (generator + QC judge)
Needs **vLLM + transformers** able to serve **Qwen2.5-72B-Instruct-AWQ**. Create a conda env (here called `fraudgen`):
```bash
conda create -y -n fraudgen python=3.10 && conda activate fraudgen
pip install -r requirements.txt
# requirements.txt pins setuptools==75.8.0 — newer setuptools breaks torch.utils.cpp_extension
# and makes `from vllm import LLM` fail with "cannot import name 'LLM'".
```
Quick check (on a GPU node):
```bash
python -c "from vllm import LLM; print('vLLM OK')"
```

## 3. Model + caches
```bash
export HF_HOME=/path/to/hf_cache           # where models are cached
export FRAUD_LLM=Qwen/Qwen2.5-72B-Instruct-AWQ   # swap model here if needed
# HF token (gated models) — keep OUT of git:
export HF_TOKEN=$(cat /path/to/.hf_token)
```
GPU: the 72B-AWQ needs **~40 GB weights + KV cache → a full A100 (40/80 GB) or H100**. A 40 GB MIG slice is too small.

## 4. Layout
```
configs/
  languages.yaml        # the 10 languages (locked)
  taxonomy.yaml         # 39 fraud types + axes
  profile_schema.yaml   # profile fields + quality guard
  entities.yaml         # real entities per region + currency + fraud_type->entity map
  seeds/<lang>.jsonl    # per-language REAL-case abstracts (with source URLs)
  seeds/_generic.jsonl  # advisory-cited generic seed per fraud type
docs/taxonomy.md        # human-readable taxonomy
scripts/
  run_profile_generation.py  # Stage 1 — profiles
  qc_profiles.py             # Stage 1 QC — near-dup + 72B judge + --apply
out/profiles/<lang>.jsonl    # GENERATED profiles (data; not in git — see §7)
```

## 5. Run Stage 1 (profiles) + QC
```bash
# generate 2000 profiles/language (resume-safe; re-run to top up)
python scripts/run_profile_generation.py --langs en hi zh ko hi-en id es vi pt ko-en --target 2000

# QC: near-dup (no GPU) + 72B quality judge; --apply removes flagged, then top up
python scripts/qc_profiles.py --langs en ... --judge --apply --target 2000
python scripts/qc_profiles.py --langs en ...            # report only (near-dup, no GPU)
```

## 5b. Continue straight from Stage 2 (no profile regeneration)
The **profiles are committed to the repo** (`out/profiles/*.jsonl`, 19,027 QC-clean, 10 langs),
so after cloning you can **skip Stage 0/1 and go straight to Stage 2** — you do NOT regenerate
profiles. Stage 2 still *generates dialogues* from them, which needs a **GPU + the 72B model**:
```bash
# (env + HF_HOME + FRAUD_LLM set as in §2–3; 72B must be cached)
# optional: top profiles up to exactly 2000/lang first (small GPU job):
python scripts/run_profile_generation.py --langs en hi zh ko hi-en id es vi pt ko-en --target 2000

# Stage 2 — two-agent dialogues (fraud + benign divergence siblings):
python scripts/run_dialogue_generation.py --langs en --limit 10 --smoke     # ~10 pairs to validate first
python scripts/run_dialogue_generation.py --langs en hi zh ko hi-en id es vi pt ko-en   # full run
# -> writes out/dialogues/<lang>.jsonl  (2 records/profile: variant=fraud|benign, shared prefix, divergence_turn)
```
Note: the committed profiles are the 19,027 QC-clean set (not yet re-topped to 2,000/lang);
either proceed as-is or run the top-up line above first.

## 6. Running under Slurm (how we do it)
Self-contained job that runs the whole finaliser on allocation (edit paths inside):
```bash
sbatch --partition=<gpu-part> --gres=gpu:a100:1 --time=08:00:00 \
       /path/to/scalign_pipeline.sh en hi zh ko hi-en
```
Tips learned the hard way:
- Use **short walls (8 h)** so the backfill scheduler slots you in sooner than long 3-day holds.
- Make the job **do the work itself** (don't rely on a login-session watcher — it can be killed).
- Do **not** use `set -e` around the pipeline (a non-fatal glitch shouldn't release the GPU).
- If a run was killed, clear GPU zombies on the node: `srun --jobid=<J> --overlap bash -lc 'for p in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader); do kill -9 $p; done'`.

## 7. The generated data
Profiles (`out/profiles/*.jsonl`, ~24 MB, 19,027 QC-clean) **are committed to the repo**, so they
arrive with `git clone` — no transfer or regeneration needed (see §5b). The broader `out/` is still
git-ignored so future **audio** (large) never bloats the repo; move audio via `rsync` when needed.
To rebuild profiles from scratch instead, the configs + scripts are all in git (run §5).

## 8. Secrets / rules
- Keep the HF token in a file **outside the repo** (`.hf_token`), never commit it.
- Commits are authored by **Girish** only.

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

## 7. Moving the generated data
Profiles live in `out/profiles/` (~24 MB for 20k) and are **git-ignored**. Either:
- **rsync** them to the new server: `rsync -av out/profiles/ newhost:.../SAFECALLALIGN/out/profiles/`, or
- **regenerate** from scratch (configs + scripts are in git): run §5. Fully reproducible.

## 8. Secrets / rules
- Keep the HF token in a file **outside the repo** (`.hf_token`), never commit it.
- Commits are authored by **Girish** only.

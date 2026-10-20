#!/bin/bash
#SBATCH --job-name=scalign-pipe
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --output=/users/msingh/GPU/%x-%j.out
#SBATCH --error=/users/msingh/GPU/%x-%j.out
# Self-contained SAFECALLALIGN profile finaliser: converges each language to 2000
# QC-clean profiles. Runs automatically when the GPU is allocated.
#   sbatch --partition=k2-gpu-a100 --gres=gpu:a100:1 --time=08:00:00 scalign_pipeline.sh en hi zh ko hi-en
export HF_HOME=/mnt/scratch2/users/msingh/hf_cache
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false
export VLLM_USE_FLASHINFER_SAMPLER=0
PY=/mnt/scratch2/users/msingh/conda/envs/fraudgen/bin/python
cd /users/msingh/Girish/SAFECALLALIGN
LANGS="$@"
echo "[pipe] $(hostname) START langs=$LANGS $(date)"
nvidia-smi -L || true

# converge: top-up to 2000 -> QC(judge+apply removes flagged) ; repeat so fresh
# top-ups also get judged. End with a final top-up so the COUNT is exactly 2000.
for R in 1 2 3; do
  echo "[pipe] === round $R: top-up generation to 2000 ==="
  $PY scripts/run_profile_generation.py --langs $LANGS --target 2000
  echo "[pipe] === round $R: QC (near-dup + 72B judge) + remove flagged ==="
  $PY scripts/qc_profiles.py --langs $LANGS --judge --apply --target 2000
done
echo "[pipe] === final top-up to exactly 2000 ==="
$PY scripts/run_profile_generation.py --langs $LANGS --target 2000
echo "[pipe] === final QC report (no apply) ==="
$PY scripts/qc_profiles.py --langs $LANGS
echo "[pipe] DONE langs=$LANGS $(date)"

#!/usr/bin/env python
"""
SAFECALLALIGN Stage 1 — profile QC (uniqueness + quality).

Two passes:
  1. NEAR-DUPLICATE (no GPU): within each (language, fraud_type) block, compute
     word-3gram Jaccard over the profile's descriptive text; flag pairs >= --jaccard
     (keep the first, flag the rest). Catches reworded repeats the exact-hash dedup misses.
  2. QUALITY JUDGE (GPU, Qwen2.5-72B): score each profile on 5 binary criteria
     (realistic, on_type, risk_node_ok, benign_ok, entity_ok); FAIL if any of
     risk_node_ok/benign_ok is 0 or total < 4.

Report -> out/profiles/qc/report.json. With --apply, rewrites <lang>.jsonl keeping only
clean+passing profiles and prints how many must be regenerated to top back up to --target
(just re-run run_profile_generation.py, which is resume-safe + deduped).

Run:
  python scripts/qc_profiles.py --langs en            # near-dup only (fast, no GPU)
  python scripts/qc_profiles.py --langs en --judge    # + LLM quality judge (GPU)
  python scripts/qc_profiles.py --langs en hi ... --judge --apply --target 2000
"""
import argparse, json, os, re, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.environ.get("FRAUD_LLM", "Qwen/Qwen2.5-72B-Instruct-AWQ")
ALL_LANGS = ["en", "hi", "zh", "ko", "hi-en", "id", "es", "vi", "pt", "ko-en"]

JSYS = (
    "You audit the quality of a fraud-call SCENARIO PROFILE (not a dialogue). Judge strictly and "
    "return ONLY compact JSON with integer 0/1 for five items:\n"
    '{"realistic":0/1,"on_type":0/1,"risk_node_ok":0/1,"benign_ok":0/1,"entity_ok":0/1}\n'
    "- realistic: a believable real-world scam scenario for its language/region.\n"
    "- on_type: matches the stated fraud_type.\n"
    "- risk_node_ok: the risk_node is a SINGLE clear pivotal unsafe moment where a fraud call and a "
    "lawful call would diverge (not vague, not multiple).\n"
    "- benign_ok: the benign_resolution plausibly shares the same opening but ends SAFELY (a real "
    "lawful version of this call).\n"
    "- entity_ok: the impersonated_entity is a real, locally-appropriate organisation for this type/region."
)


def text_of(p):
    return " ".join(str(p.get(k, "")) for k in
                    ("grounding_summary", "initial_event", "risk_node", "benign_resolution")).lower()


def shingles(t, n=3):
    w = re.findall(r"\w+", t)
    return set(tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))) or {("",)}


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 0.0


def near_dup_flags(rows, thr):
    """greedy keep-first within (fraud_type) blocks; return set of flagged indices."""
    flagged = set()
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r.get("fraud_type", "")].append(i)
    for _ft, idxs in by.items():
        sh = {i: shingles(text_of(rows[i])) for i in idxs}
        kept = []
        for i in idxs:
            if any(jaccard(sh[i], sh[j]) >= thr for j in kept):
                flagged.add(i)
            else:
                kept.append(i)
    return flagged


def run_judge(rows, sample):
    """returns dict idx->(pass_bool, scores). Uses vLLM 72B."""
    idxs = list(range(len(rows)))
    if sample and sample < len(idxs):
        import random
        random.Random(0).shuffle(idxs); idxs = sorted(idxs[:sample])
    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    prompts = []
    for i in idxs:
        p = rows[i]
        u = (f"fraud_type: {p.get('fraud_type')}\nlanguage: {p.get('language')}\n"
             f"impersonated_entity: {p.get('impersonated_entity')}\n"
             f"grounding_summary: {p.get('grounding_summary')}\ninitial_event: {p.get('initial_event')}\n"
             f"risk_node: {p.get('risk_node')}\nbenign_resolution: {p.get('benign_resolution')}\n\nScore now as JSON.")
        prompts.append(tok.apply_chat_template(
            [{"role": "system", "content": JSYS}, {"role": "user", "content": u}],
            tokenize=False, add_generation_prompt=True))
    llm = LLM(model=MODEL, max_model_len=4096, gpu_memory_utilization=0.92,
              quantization="awq" if "AWQ" in MODEL else None)
    outs = llm.generate(prompts, SamplingParams(temperature=0.0, max_tokens=60))
    res = {}
    for i, o in zip(idxs, outs):
        m = re.search(r"\{.*\}", o.outputs[0].text, re.DOTALL)
        try:
            j = json.loads(m.group(0)) if m else {}
        except Exception:
            j = {}
        s = {k: int(bool(j.get(k, 0))) for k in ("realistic", "on_type", "risk_node_ok", "benign_ok", "entity_ok")}
        ok = s["risk_node_ok"] == 1 and s["benign_ok"] == 1 and sum(s.values()) >= 4
        res[i] = (ok, s)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="+", default=["en"])
    ap.add_argument("--jaccard", type=float, default=0.7)
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--judge-sample", type=int, default=0, help="0 = judge all")
    ap.add_argument("--apply", action="store_true", help="rewrite <lang>.jsonl keeping clean+passing only")
    ap.add_argument("--target", type=int, default=2000)
    args = ap.parse_args()

    qcdir = os.path.join(HERE, "out", "profiles", "qc"); os.makedirs(qcdir, exist_ok=True)
    report = {}
    for lang in args.langs:
        path = os.path.join(HERE, "out", "profiles", f"{lang}.jsonl")
        if not os.path.exists(path):
            print(f"[qc] {lang}: no file, skip"); continue
        rows = [json.loads(l) for l in open(path, encoding="utf-8")]
        nd = near_dup_flags(rows, args.jaccard)
        judge = run_judge(rows, args.judge_sample) if args.judge else {}
        judged = [i for i in judge]
        jfail = {i for i, (ok, _) in judge.items() if not ok}
        flagged = nd | jfail
        clean = [r for i, r in enumerate(rows) if i not in flagged]
        cov = collections.Counter(r.get("fraud_type") for r in rows)
        rep = {"lang": lang, "n": len(rows), "near_dup": len(nd),
               "judged": len(judged), "judge_fail": len(jfail),
               "judge_pass_rate": (round((len(judged) - len(jfail)) / len(judged), 3) if judged else None),
               "flagged_total": len(flagged), "clean": len(clean),
               "need_regen_to_target": max(0, args.target - len(clean)),
               "type_coverage": dict(cov)}
        report[lang] = rep
        json.dump(sorted(flagged), open(os.path.join(qcdir, f"{lang}_flagged.json"), "w"))
        print(f"[qc] {lang}: n={rep['n']} near_dup={rep['near_dup']} "
              f"judge_fail={rep['judge_fail']} pass_rate={rep['judge_pass_rate']} "
              f"clean={rep['clean']} regen_needed={rep['need_regen_to_target']}", flush=True)
        if args.apply:
            with open(path, "w", encoding="utf-8") as f:
                for r in clean:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"[qc] {lang}: rewrote {len(clean)} clean profiles (re-run generator to top up to {args.target})", flush=True)
    json.dump(report, open(os.path.join(qcdir, "report.json"), "w"), ensure_ascii=False, indent=1)
    print(f"[qc] report -> {os.path.relpath(os.path.join(qcdir,'report.json'), HERE)}")


if __name__ == "__main__":
    main()

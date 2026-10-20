#!/usr/bin/env python
"""
SAFECALLALIGN Stage 1 — profile grounding (wired + deduped).

For each language, builds a seed pool = the language's REAL per-URL case abstracts
(configs/seeds/<lang>.jsonl) overlaid on the GENERIC per-type advisory abstracts
(configs/seeds/_generic.jsonl), so ALL fraud types are covered while prevalent types
stay grounded in real cases. Expands the pool into native profiles up to --target per
language, with LIVE exact-dedup (drop + regenerate so we land exactly --target UNIQUE
profiles). Controlled fields (fraud_type/super_category) are forced from the seed.

Run (fraudgen env, full GPU):
    python scripts/run_profile_generation.py --langs en --target 100
    python scripts/run_profile_generation.py --langs en hi zh ko id es vi pt hi-en ko-en --target 2000
"""
import argparse, json, os, re, itertools, hashlib, glob, random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.environ.get("FRAUD_LLM", "Qwen/Qwen2.5-72B-Instruct-AWQ")

SUPER_OF = {}
for _sc, _types in {
    "impersonation": ["customer_service", "bank", "tech_support", "government_impersonation",
                      "courier_collection", "electricity_utility", "trai_sim_disconnection",
                      "marketplace", "charity_donation", "messenger_phishing", "card_pickup_courier",
                      "credit_repair", "immigration_embassy", "recovery_refund"],
    "investment_lure": ["investment", "pig_butchering", "lottery", "romance", "job_task",
                        "insurance", "task_rebate", "advance_fee"],
    "credential_compromise": ["phishing", "email", "bec", "identity_theft", "upi_payment",
                              "kyc_update", "sim_swap", "malicious_apk", "skimming",
                              "account_mule", "account_takeover", "pix_payment"],
    "coercion_threat": ["kidnapping", "extortion_sextortion", "family_emergency", "digital_arrest",
                        "loan_app", "loan_solicitation", "customs_courier"],
}.items():
    for _t in _types:
        SUPER_OF[_t] = _sc

LANG_NAME = {"en": "English", "zh": "Chinese (Mandarin)", "ko": "Korean", "hi": "Hindi",
             "id": "Indonesian", "es": "Spanish", "vi": "Vietnamese", "pt": "Portuguese (Brazilian)",
             "hi-en": "Hinglish (Hindi-English code-switch)", "ko-en": "Konglish (Korean-English code-switch)"}
BASE_OF = {"hi-en": "hi", "ko-en": "ko"}   # code-switch inherits base-language real seeds

SYS = (
    "You design GROUNDED fraud-call scenario profiles for a safety research dataset. "
    "Given a real-case abstract and a target language, output DIVERSE, realistic profiles "
    "native to that language/culture (not translated). A profile GUIDES generation; it must "
    "support BOTH a fraud path and a near-domain LAWFUL sibling sharing the same opening up to "
    "the risk_node.\n"
    "REALISM: use REAL, locally-recognised entity names (banks, agencies, couriers, apps, platforms) "
    "that scammers plausibly IMPERSONATE, and the native CURRENCY with realistic local amounts. "
    "SAFETY: never use real working phone numbers, URLs, links, or account numbers — use obvious "
    "placeholders for those. No real personal data. Return STRICT JSON only."
)

SCHEMA_HINT = """Real-case abstract (fraud_type={ftype}, region={region}):
"{abstract}"
Safe verification channel: {svc}

REALISM for these profiles: currency = {currency}; the scammer impersonates a REAL entity such as: {entities} (pick one per profile and name it explicitly in caller_role/grounding_summary; vary across profiles). Use realistic local amounts in {currency}. Use obvious placeholders for any phone number/link/account (never real ones).

Return a JSON array of {n} DISTINCT profile objects for language={lang} ({lang_name}). Each EXACTLY:
{{
 "grounding_summary": "<1-2 sentence PII-free modus operandi, native to {lang_name}, naming the real entity>",
 "impersonated_entity": "<the real entity this profile's scammer impersonates>",
 "caller_role": "<who the scammer claims to be>",
 "receiver_profile": "<brief victim persona, native to {lang_name}>",
 "initial_event": "<the pretext/hook opening the call>",
 "risk_node": "<the single pivotal unsafe moment where fraud and a lawful call diverge>",
 "requested_action": "<unsafe ask, e.g. otp_or_verification_code / transfer_or_pay_money / install_app_or_remote_access>",
 "planned_tactics": ["<2-4 of: authority, urgency, fear, affinity, reward, social_proof, commitment, isolation, credential_request>"],
 "channel": "<voice_call / vishing_spoofed_callerid / smishing_sms / whatsapp_or_messenger / callback_number>",
 "safe_verification_channel": "<what a LEGITIMATE call/entity would advise instead>",
 "benign_resolution": "<how the lawful sibling safely resolves after the shared opening>"
}}
Make the {n} profiles clearly DIFFERENT (varied caller roles, victims, events, stakes). No markdown, just the JSON array."""


def extract_json_array(t):
    t = t.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(json)?", "", t).rsplit("```", 1)[0]
    m = re.search(r"\[.*\]", t, re.DOTALL)
    raw = m.group(0) if m else t
    try:
        return json.loads(raw)
    except Exception:
        try:
            from json_repair import repair_json
            return json.loads(repair_json(raw))
        except Exception:
            return None


def load_seed_pool(lang):
    """generic per-type seeds overlaid with the language's (or base lang's) real seeds."""
    pool = {}
    gpath = os.path.join(HERE, "configs", "seeds", "_generic.jsonl")
    for l in open(gpath, encoding="utf-8"):
        s = json.loads(l); pool[s["fraud_type"]] = dict(s, grounded="advisory")
    real_lang = BASE_OF.get(lang, lang)
    rpath = os.path.join(HERE, "configs", "seeds", f"{real_lang}.jsonl")
    if os.path.exists(rpath):
        for l in open(rpath, encoding="utf-8"):
            s = json.loads(l); pool[s["fraud_type"]] = dict(s, grounded="real_case")
    return list(pool.values())


def load_entities():
    import yaml
    return yaml.safe_load(open(os.path.join(HERE, "configs", "entities.yaml"), encoding="utf-8"))


def pick_entities(ENT, lang, fraud_type, k=4):
    """return (currency_symbol, [candidate real entities]) for this lang+fraud_type."""
    cur = ENT["currency"].get(lang, {}).get("symbol", "")
    elang = BASE_OF.get(lang, lang)   # code-switch inherits base-lang entity lists
    cats = ENT["fraud_type_entities"].get(fraud_type, [])
    cand = []
    for c in cats:
        cand += ENT["entities"].get(elang, {}).get(c, [])
    cand = [x for x in cand if x]
    random.shuffle(cand)
    return cur, cand[:k] if cand else ["a well-known local institution"]


def sig(p):
    key = f"{p.get('caller_role','')}|{p.get('initial_event','')}|{p.get('risk_node','')}".lower()
    return hashlib.md5(re.sub(r"\s+", " ", key).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="+", default=["en"])
    ap.add_argument("--target", type=int, default=2000)
    ap.add_argument("--per-call", type=int, default=4, help="profiles requested per seed per round")
    ap.add_argument("--max-rounds", type=int, default=40)
    ap.add_argument("--max-model-len", type=int, default=4096)
    ap.add_argument("--out-dir", default=os.path.join(HERE, "out", "profiles"))
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        args.langs = args.langs[:1]; args.target = 12; args.max_rounds = 2

    os.makedirs(args.out_dir, exist_ok=True)
    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    llm = LLM(model=MODEL, max_model_len=args.max_model_len, gpu_memory_utilization=0.92,
              quantization="awq" if "AWQ" in MODEL else None)
    sp = SamplingParams(temperature=1.0, top_p=0.95, max_tokens=2600)

    REQ = ["grounding_summary", "impersonated_entity", "caller_role", "receiver_profile",
           "initial_event", "risk_node", "requested_action", "safe_verification_channel", "benign_resolution"]
    ENT = load_entities()

    for lang in args.langs:
        pool = load_seed_pool(lang)
        cur = ENT["currency"].get(lang, {}).get("symbol", "")
        out_path = os.path.join(args.out_dir, f"{lang}.jsonl")
        recs = [json.loads(l) for l in open(out_path, encoding="utf-8")] if os.path.exists(out_path) else []
        seen = set(sig(r) for r in recs)
        gc = itertools.cycle([("male", "female"), ("female", "male"), ("male", "male"), ("female", "female")])
        for _ in range(len(recs)):
            next(gc)
        dup = pf = 0
        print(f"[profiles] {lang}: start={len(recs)} target={args.target} pool_types={len(pool)}", flush=True)
        for rnd in range(args.max_rounds):
            if len(recs) >= args.target:
                break
            prompts, metas = [], []
            for s in pool:
                _cur, _cands = pick_entities(ENT, lang, s["fraud_type"])
                user = SCHEMA_HINT.format(n=args.per_call, ftype=s["fraud_type"], region=s.get("region", "global"),
                                          abstract=s["abstract"], svc=s.get("safe_verification_channel", ""),
                                          lang=lang, lang_name=LANG_NAME.get(lang, lang),
                                          currency=_cur or "local currency", entities=", ".join(_cands))
                prompts.append(tok.apply_chat_template(
                    [{"role": "system", "content": SYS}, {"role": "user", "content": user}],
                    tokenize=False, add_generation_prompt=True))
                metas.append(s)
            outs = llm.generate(prompts, sp)
            for s, o in zip(metas, outs):
                if len(recs) >= args.target:
                    break
                arr = extract_json_array(o.outputs[0].text) or []
                if not isinstance(arr, list):
                    continue
                for p in arr:
                    if len(recs) >= args.target:
                        break
                    if not isinstance(p, dict) or any(not p.get(k) for k in REQ):
                        pf += 1; continue
                    if sig(p) in seen:
                        dup += 1; continue
                    seen.add(sig(p))
                    cg, eg = next(gc)
                    p["fraud_type"] = s["fraud_type"]
                    p["super_category"] = SUPER_OF.get(s["fraud_type"], "")
                    p["language"] = lang
                    p["region"] = s.get("region", "global")
                    p["case_source"] = s.get("source_url") or s.get("case_id")
                    p["grounded"] = s.get("grounded", "advisory")
                    p["currency"] = cur
                    p["caller_gender"], p["callee_gender"] = cg, eg
                    p["profile_id"] = f"{lang}_{s['fraud_type']}_{sum(1 for r in recs if r['fraud_type']==s['fraud_type'])+1:04d}"
                    recs.append(p)
            with open(out_path, "w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"[profiles] {lang}: round{rnd} kept={len(recs)}/{args.target} dup_dropped={dup} parse_fail={pf}", flush=True)
            if args.smoke:
                break
        status = "DONE" if len(recs) >= args.target else "SHORT(max_rounds)"
        print(f"[profiles] {lang}: {status} {len(recs)} unique (dup_dropped={dup} parse_fail={pf}) -> {os.path.relpath(out_path, HERE)}", flush=True)


if __name__ == "__main__":
    main()

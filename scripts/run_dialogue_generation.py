#!/usr/bin/env python
"""
SAFECALLALIGN Stage 2 — two-agent dialogue generation + divergence-point siblings.

For each Stage-1 profile we produce a matched PAIR that shares an identical opening
and FORKS at the risk_node (= the divergence point / T_c):
  * SHARED PREFIX  — a fraudster-agent and a victim-agent exchange a neutral opening
                     (caller states the pretext; victim engages) BEFORE any unsafe ask.
  * FRAUD branch   — the fraudster pushes the unsafe ask (risk_node); the victim-agent,
                     with a sampled RESISTANCE level, may comply / hesitate / refuse.
  * BENIGN branch  — a LEGITIMATE version of the same entity resolves the matter
                     lawfully (via safe_verification_channel); no unsafe ask.

Emergent, not scripted: each turn is a separate in-character generation that only sees
the conversation so far. Batched ACROSS dialogues per speaker for vLLM efficiency.
Realism: native language + real entity + native currency; placeholders for any working
phone/link/account.

Output: out/dialogues/<lang>.jsonl — two records per profile (variant=fraud|benign),
sharing prefix turns, with divergence_turn (T_c), resistance, pace, + profile labels.

Run (fraudgen env, full GPU):
    python scripts/run_dialogue_generation.py --langs en --limit 10 --smoke   # short validation set
    python scripts/run_dialogue_generation.py --langs en hi ... --per-lang 2000
"""
import argparse, json, os, re, random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.environ.get("FRAUD_LLM", "Qwen/Qwen2.5-72B-Instruct-AWQ")
LANG_NAME = {"en": "English", "zh": "Chinese", "ko": "Korean", "hi": "Hindi", "id": "Indonesian",
             "es": "Spanish", "vi": "Vietnamese", "pt": "Portuguese (Brazilian)",
             "hi-en": "Hinglish (Hindi-English code-switch)", "ko-en": "Konglish (Korean-English code-switch)"}

RESISTANCE = {
    "compliant": "trusting and cooperative; you tend to believe the caller and go along unless something is blatantly wrong",
    "skeptical": "cautious; you ask verifying questions and hesitate before doing anything sensitive",
    "resistant": "wary; you push back, try to verify independently, and are likely to refuse risky requests",
}
PACE = {"slow": "build rapport over several turns before the key ask",
        "moderate": "get to the point at a normal pace",
        "fast": "create urgency and reach the key ask quickly"}

PREFIX_TURNS = 3          # shared opening: caller, victim, caller
FRAUD_CONT   = 6          # fraud continuation turns
BENIGN_CONT  = 4          # benign continuation turns


def neutral_sys(p, lang):
    return (f"You role-play a caller from {p.get('impersonated_entity')} OPENING a "
            f"{LANG_NAME.get(lang,lang)} phone call. Introduce yourself and state the reason for calling, "
            f"based on: {p.get('initial_event')} This is only the OPENING — do NOT yet request any code, "
            f"password, card detail, money, app install, or action; just set up the matter naturally. "
            f"Write ONE short, natural spoken line in {LANG_NAME.get(lang,lang)}. No narration.")


def fraud_sys(p, lang):
    return (f"You role-play a FRAUDSTER in a {LANG_NAME.get(lang,lang)} phone scam, for a safety-research "
            f"dataset. You are '{p.get('caller_role')}', impersonating {p.get('impersonated_entity')}. "
            f"Scenario: {p.get('grounding_summary')} You will {PACE.get(p.get('_pace','moderate'))}; use pressure "
            f"tactics ({', '.join(p.get('planned_tactics',[])[:4])}) and steer toward the unsafe action at the "
            f"risk point: {p.get('risk_node')} (requested action: {p.get('requested_action')}). "
            f"Use real entity names and {p.get('currency','local')} amounts; use obvious placeholders for any "
            f"phone number/link/account (never real ones). Write ONE short, natural spoken line in "
            f"{LANG_NAME.get(lang,lang)}. Stay in character; no narration, no stage directions.")


def legit_sys(p, lang):
    return (f"You role-play a LEGITIMATE caller from {p.get('impersonated_entity')} in a "
            f"{LANG_NAME.get(lang,lang)} phone call (NOT a scam). Opening matter: {p.get('initial_event')} "
            f"Resolve it lawfully and reassuringly: {p.get('benign_resolution')} If any verification is needed, "
            f"direct the user to {p.get('safe_verification_channel')}. NEVER ask for OTP/passwords/card details "
            f"or a money transfer. Write ONE short, natural spoken line in {LANG_NAME.get(lang,lang)}. "
            f"No narration.")


def victim_sys(p, lang, resistance):
    return (f"You role-play the CALLEE (potential victim) in a {LANG_NAME.get(lang,lang)} phone call. "
            f"Persona: {p.get('receiver_profile')}. Disposition: you are {RESISTANCE[resistance]}. "
            f"Respond ONE short, natural spoken line in {LANG_NAME.get(lang,lang)}, in character, reacting to "
            f"what the caller just said. No narration.")


def transcript(turns):
    return "\n".join(f"{'Caller' if t['speaker']=='caller' else 'Callee'}: {t['text']}" for t in turns)


def clean_line(t):
    t = (t or "").strip().strip('"')
    t = re.sub(r'^(Caller|Callee|CALLER|CALLEE)\s*[:：-]\s*', '', t).strip()
    return t.split("\n")[0].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="+", default=["en"])
    ap.add_argument("--per-lang", type=int, default=0, help="0 = all profiles")
    ap.add_argument("--limit", type=int, default=0, help="cap profiles (for a short validation set)")
    ap.add_argument("--max-model-len", type=int, default=4096)
    ap.add_argument("--out-dir", default=os.path.join(HERE, "out", "dialogues"))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    if args.smoke:
        args.langs = args.langs[:1]; args.limit = args.limit or 6
    rng = random.Random(args.seed)
    os.makedirs(args.out_dir, exist_ok=True)

    from vllm import LLM, SamplingParams
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    llm = LLM(model=MODEL, max_model_len=args.max_model_len, gpu_memory_utilization=0.92,
              quantization="awq" if "AWQ" in MODEL else None)
    sp = SamplingParams(temperature=1.0, top_p=0.95, max_tokens=120)

    def gen_turn(items, speaker, sys_of):
        """items: list of dicts each with 'turns' + profile 'p' + 'lang' + 'resistance'.
        Generate the next line for `speaker` in each, append to its 'turns'. Batched."""
        prompts = []
        for it in items:
            sysmsg = sys_of(it)
            user = (f"Conversation so far:\n{transcript(it['turns']) or '(call just connected)'}\n\n"
                    f"Write ONLY the {'caller' if speaker=='caller' else 'callee'}'s next line.")
            prompts.append(tok.apply_chat_template(
                [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}],
                tokenize=False, add_generation_prompt=True))
        outs = llm.generate(prompts, sp)
        for it, o in zip(items, outs):
            it["turns"].append({"speaker": speaker, "text": clean_line(o.outputs[0].text)})

    for lang in args.langs:
        pf = os.path.join(HERE, "out", "profiles", f"{lang}.jsonl")
        if not os.path.exists(pf):
            print(f"[dlg] {lang}: no profiles, skip"); continue
        profs = [json.loads(l) for l in open(pf, encoding="utf-8")]
        if args.per_lang:
            profs = profs[:args.per_lang]
        if args.limit:
            profs = profs[:args.limit]
        # per-profile sampled dynamics
        items = []
        for p in profs:
            res = rng.choice(["compliant", "skeptical", "resistant"])
            p["_pace"] = rng.choice(["slow", "moderate", "fast"])
            items.append({"p": p, "lang": lang, "resistance": res, "turns": []})
        print(f"[dlg] {lang}: {len(items)} profiles -> fraud+benign pairs", flush=True)

        # ---- SHARED PREFIX (caller=fraudster-neutral opening, victim, caller) ----
        # the prefix caller uses the fraud persona but only the pretext (pre-ask), so it is
        # a plausible opening for BOTH branches; victim reacts per resistance.
        for i in range(PREFIX_TURNS):
            spk = "caller" if i % 2 == 0 else "callee"
            if spk == "caller":
                gen_turn(items, "caller", lambda it: neutral_sys(it["p"], it["lang"]))
            else:
                gen_turn(items, "callee", lambda it: victim_sys(it["p"], it["lang"], it["resistance"]))
        # snapshot the shared prefix
        for it in items:
            it["prefix"] = [dict(t) for t in it["turns"]]

        # ---- FRAUD branch ----
        for it in items:
            it["turns"] = [dict(t) for t in it["prefix"]]
        nxt = "callee" if PREFIX_TURNS % 2 == 1 else "caller"
        for i in range(FRAUD_CONT):
            spk = nxt if i == 0 else ("caller" if prev == "callee" else "callee")
            if spk == "caller":
                gen_turn(items, "caller", lambda it: fraud_sys(it["p"], it["lang"]))
            else:
                gen_turn(items, "callee", lambda it: victim_sys(it["p"], it["lang"], it["resistance"]))
            prev = spk
        for it in items:
            it["fraud_turns"] = it["turns"]

        # ---- BENIGN branch (legit caller) ----
        for it in items:
            it["turns"] = [dict(t) for t in it["prefix"]]
        for i in range(BENIGN_CONT):
            spk = nxt if i == 0 else ("caller" if prev == "callee" else "callee")
            if spk == "caller":
                gen_turn(items, "caller", lambda it: legit_sys(it["p"], it["lang"]))
            else:
                gen_turn(items, "callee", lambda it: victim_sys(it["p"], it["lang"], "skeptical"))
            prev = spk
        for it in items:
            it["benign_turns"] = it["turns"]

        # ---- write pairs ----
        out = os.path.join(args.out_dir, f"{lang}.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for it in items:
                p = it["p"]
                base = {k: p.get(k) for k in ("profile_id", "fraud_type", "super_category", "language",
                                              "impersonated_entity", "currency", "requested_action",
                                              "planned_tactics", "caller_gender", "callee_gender", "case_source")}
                base.update({"resistance": it["resistance"], "pace": p["_pace"],
                             "divergence_turn": len(it["prefix"])})
                f.write(json.dumps({**base, "id": f"{p['profile_id']}__fraud", "is_fraud": True,
                                    "variant": "fraud", "turns": it["fraud_turns"]}, ensure_ascii=False) + "\n")
                f.write(json.dumps({**base, "id": f"{p['profile_id']}__benign", "is_fraud": False,
                                    "variant": "benign", "turns": it["benign_turns"]}, ensure_ascii=False) + "\n")
        print(f"[dlg] {lang}: wrote {2*len(items)} dialogues ({len(items)} fraud+benign pairs) -> {os.path.relpath(out, HERE)}", flush=True)


if __name__ == "__main__":
    main()

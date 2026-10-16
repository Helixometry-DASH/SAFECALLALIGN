# SAFECALLALIGN — Fraud Taxonomy (Stage 0, finalized 2026-10-15)

A multilingual, authority-grounded taxonomy for phone-call fraud/benign dialogue.
**39 fraud types + 2 subtypes** across **4 super-categories**, labeled on **6 axes**,
grounded in **8 national authorities** + global completeness sources. Benign calls are
**near-domain lawful siblings** of fraud types, not an independent set.

Machine-readable source of truth: [`configs/taxonomy.yaml`](../configs/taxonomy.yaml).
Languages: [`configs/languages.yaml`](../configs/languages.yaml).

---

## 1. Languages (10)

| Type | Languages |
|---|---|
| Monolingual (8) | English `en`, Chinese `zh`, Korean `ko`, Hindi `hi`, Indonesian `id`, Spanish `es`, Vietnamese `vi`, Portuguese-BR `pt` |
| Code-switch (2) | Hinglish `hi-en`, Konglish `ko-en` |

Code-switch variants inherit their base languages' fraud types (India / Korea).

---

## 2. Labeling axes (every call)

| Axis | Meaning | Values |
|---|---|---|
| A. `fraud_type` | what kind of scam | 39 types (below) |
| B. `impersonated_entity` | who they pretend to be | bank / govt-police / tech / company / family / none |
| C. `manipulation_tactics` | how they pressure (multi-label) | authority, urgency, affinity, reward, social_proof, commitment, fear, isolation, credential_request (Cialdini + fear) |
| D. `requested_action` | the unsafe ask | otp, transfer, card/bank, password/pin, install/remote, link, identity_info, gift_cards, crypto, none, other |
| E. `compliance_level` | how far the victim went | none / partial / full |
| F. `channel` | contact/escalation vector | voice_call, callback, vishing_spoofed_callerid, smishing, whatsapp/messenger, email, link, apk, qr |

---

## 3. Fraud types by super-category

### ① Impersonation (14)
| Type | Gloss | Origin region | Maps to seed |
|---|---|---|---|
| customer_service | fake support/service rep | seed | — |
| bank | fake bank/card-issuer | seed | — |
| tech_support | fake tech/remote-access support | US | — |
| government_impersonation | police/tax/court/agency | US | — |
| courier_collection | fake courier collects cash/gold | US | — |
| electricity_utility | utility cut-off threat | India | government_impersonation |
| trai_sim_disconnection | telecom/SIM-block threat | India | government_impersonation |
| marketplace | fake buyer/seller (OLX/FB) | India/global | courier_collection |
| charity_donation | fake charity/disaster relief | India/global | — |
| messenger_phishing | KakaoTalk family/acquaintance | Korea | family_emergency |
| card_pickup_courier | "motoboy" collects physical card | Brazil/global | courier_collection |
| credit_repair | fix bad credit-record scam | China | — |
| immigration_embassy | visa/immigration/embassy "fix status, pay fee" | US/global | government_impersonation |
| recovery_refund | fake refund (remote-access) + "recover your lost funds" re-victimization | US/global | — |

### ② Investment / financial lure (7 + 1 subtype)
| Type | Gloss | Origin | Maps to seed |
|---|---|---|---|
| investment | fake investment/wealth-mgmt | seed | — |
| ↳ pig_butchering | long-con crypto/relationship investment | US | (subtype of investment) |
| lottery | prize/sweepstakes/inheritance | seed | — |
| romance | romance → money/invest | US | — |
| job_task | job / work-from-home | US | — |
| insurance | fake policy/bonus release | India | — |
| task_rebate | order-brushing / commission task (刷单返利) | China | job_task |
| advance_fee | 419 / inheritance / fee-to-release | global | lottery |

### ③ Credential / account compromise (11 + 1 subtype)
| Type | Gloss | Origin | Maps to seed |
|---|---|---|---|
| phishing | steal credentials/OTP | seed | — |
| email | email-based fraud | seed | — |
| ↳ bec | business email / payment redirection | US | (subtype of email) |
| identity_theft | steal identity/PII | seed | — |
| upi_payment | UPI instant-rail fraud | India | bank |
| kyc_update | fake KYC-update/refund | India | phishing |
| sim_swap | SIM-swap takeover | India/global | identity_theft |
| malicious_apk | APK file → banking trojan | Indonesia/global | — |
| skimming | card skimming / data capture | Indonesia/global | identity_theft |
| account_mule | money-mule / bankbook lending | Korea/global | — |
| account_takeover | WhatsApp cloning via security code | Brazil/global | phishing |
| pix_payment | Pix instant-rail fraud | Brazil | upi_payment |

### ④ Coercion / threat / extortion (7)
| Type | Gloss | Origin | Maps to seed |
|---|---|---|---|
| kidnapping | (virtual) kidnapping | seed | — |
| extortion_sextortion | extortion / sextortion / naked-chat | US | — |
| family_emergency | "relative in trouble" / grandparent | US | kidnapping |
| digital_arrest | prolonged police/court "arrest" intimidation | India | government_impersonation |
| loan_app | predatory loan app + blackmail | India | — |
| loan_solicitation | fake loan offer → harvest card/bankbook | Korea | loan_app |
| customs_courier | customs/parcel threat (drugs/Aadhaar) | India/global | courier_collection |

---

## 4. Stats

### By super-category
| Super-category | Types | Subtypes |
|---|---:|---:|
| ① Impersonation | 14 | 0 |
| ② Investment / lure | 7 | 1 (pig_butchering) |
| ③ Credential / compromise | 11 | 1 (bec) |
| ④ Coercion / threat | 7 | 0 |
| **Total** | **39** | **2** |

### New types contributed per region (grounding)
| Region | Source authority | New types |
|---|---|---:|
| Seed (TeleAntiFraud-28k + prior) | MPS / FraudAlign-MCS | 8 |
| US / global | FBI IC3, FTC | 7 (+2 subtypes) |
| India | I4C/NCRP, RBI, TRAI | 11 |
| Korea | FSS, KNPA | 3 |
| Indonesia | OJK, Satgas PASTI | 2 |
| Spain | INCIBE | 0 (added channel axis) |
| Vietnam | MPS, NCA | 0 (broadened regions) |
| Brazil | Febraban, BCB | 3 |
| China | MPS 公安部 | 2 |
| Completeness pass | ACCC, FTC, GSMA, USCIS | 3 |
| **Total** | | **39 (+2)** |

### Benign (near-domain siblings)
One lawful sibling per fraud type (shared domain/prefix) + pure-benign set:
`delivery, appointment, survey, personal, utility`.

---

## 5. Comparison to prior work
| | TeleAntiFraud-28k | TeleAntiFraud 2.0 | **SAFECALLALIGN** |
|---|---|---|---|
| Fraud types | 7 (fixed) | open `fraud_family` (demo: 2) | **39 (+2 subtypes)** |
| Languages | Chinese | Chinese | **10 (8 base + 2 code-switch)** |
| Grounding regions | 1 (CN) | 1 (CN) | **8 + global** |
| Labeling axes | type + is_fraud | type + is_fraud | **6 axes** |
| Hard negatives | — | near-domain siblings | **divergence-point siblings** |
| Excluded | — | — | wangiri (non-conversational) |

Every type carries `regions` + `sources` provenance in `configs/taxonomy.yaml`.

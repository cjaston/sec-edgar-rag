# Test: Pharmaceutical Regulatory Risks
**Model:** openai/gpt-4o
**Date:** 2026-03-13
**Mode:** Verbose
**Latency:** 8,081ms
**Tokens:** 15,181 in / 819 out
**Chunks:** 30 retrieved → 10 used

## Rate Limit Notes
- OpenAI TPM limit: 30,000 tokens/minute (Tier 1)
- **Original 18-chunk attempt (27K tokens) was rejected** — "Requested 38,547" exceeded 30K TPM
- **14-chunk attempt (21K tokens) also failed** — previous query's tokens hadn't fully cleared the per-minute window
- **10-chunk attempt (15K tokens) succeeded** after a 60-second cooldown
- OpenAI enforces TPM as a **per-request ceiling** (input + max_output_tokens counted together)
- Anthropic uses a **token bucket** model — allows bursts, which is why the same 18-chunk/27K prompt succeeded on Claude
- This means GPT-4o received significantly less context (10 chunks vs Claude's 18) for this query

## Question
What regulatory risks do the major pharmaceutical companies face, and how are they addressing them?

## Pipeline Details
- **Tickers detected:** (none — sector-based query)
- **Sectors detected:** pharma
- **Section hint:** Risk Factors
- **Retrieval:** Standard sector-filtered
- **Where clause:** `{'sector': 'pharma'}`

## Model Response

**Regulatory Risks and Responses of Major Pharmaceutical Companies**

**Johnson & Johnson (JNJ)**
- **Regulatory Environment**: JNJ faces stringent regulations in the U.S. and internationally, particularly concerning product safety, efficacy, manufacturing, and advertising. The trend is towards more stringent regulation and enforcement [JNJ, 10-K, 2022-02-17, Item 8].
- **Compliance and Enforcement**: The U.S. FDA and other global regulatory bodies have broad powers, including product recalls and imposing civil or criminal penalties. Non-compliance could lead to significant business disruptions [JNJ, 10-K, 2022-02-17, Item 8].
- **Healthcare Costs and Legislation**: JNJ is affected by U.S. healthcare reforms, including the Affordable Care Act and the Inflation Reduction Act, which impact drug pricing and reimbursement [JNJ, 10-K, 2023-02-16, Item 8].
- **Data Privacy and Cybersecurity**: Increasing global privacy regulations require JNJ to ensure compliance, particularly with new laws in the U.S. and China [JNJ, 10-K, 2023-02-16, Item 8].

**Pfizer (PFE)**
- **Government Regulation**: Pfizer is subject to extensive regulation, including drug approval, manufacturing, and marketing. Non-compliance can lead to fines, product recalls, and business restrictions [PFE, 10-K, 2024-02-22, Risk Factors].
- **Pricing Pressures**: Managed Care Organizations (MCOs) and government programs exert pressure on drug pricing, affecting Pfizer's revenues. The company is actively managing these pressures through strategic pricing and reimbursement strategies [PFE, 10-K, 2024-02-22, Risk Factors].
- **340B Program**: Pfizer faces regulatory scrutiny and potential legal challenges related to the 340B Drug Pricing Program, which requires offering discounts to covered entities [PFE, 10-K, 2024-02-22, Risk Factors].
- **Data Privacy**: Increasing privacy and data protection laws pose compliance challenges, with potential fines and reputational risks for non-compliance [PFE, 10-K, 2024-02-22, Risk Factors].

**Merck (MRK)**
- **Medicare and Medicaid Changes**: The Inflation Reduction Act introduces government price setting for certain drugs, impacting Merck's pricing strategy and potentially reducing revenues [MRK, 10-K, 2025-02-25, Business].
- **Regulatory Approvals**: Merck's ability to market new products depends on obtaining and maintaining regulatory approvals, which are subject to stringent requirements and potential delays [MRK, 10-K, 2025-02-25, Business].
- **Post-Approval Risks**: Developments after regulatory approval, such as adverse trial results or increased scrutiny, can negatively impact product sales [MRK, 10-K, 2025-02-25, Business].

**Eli Lilly (LLY)**
- **Patent Challenges**: LLY faces patent challenges, including inter partes review processes that can invalidate patents, affecting its competitive position [LLY, 10-K, 2026-02-12, Business].
- **Regulatory Compliance**: Extensive regulation by the FDA and international bodies requires significant investment in compliance, with risks of enforcement actions for non-compliance [LLY, 10-K, 2026-02-12, Business].
- **Manufacturing Quality**: Compliance with cGMP regulations is critical, with potential for significant business impacts from regulatory actions related to manufacturing deficiencies [LLY, 10-K, 2026-02-12, Business].

**Conclusion**
- Major pharmaceutical companies face significant regulatory risks related to compliance with stringent laws, pricing pressures, and data privacy requirements.
- Companies are addressing these risks through strategic compliance investments, legal challenges, and adapting to changing regulatory landscapes.

## Sources
- Johnson & Johnson (JNJ) — 10-K 2022-02-17, Item 8
- Pfizer Inc (PFE) — 10-K 2024-02-22, Risk Factors
- Pfizer Inc (PFE) — 10-K 2023-02-23, Risk Factors
- Johnson & Johnson (JNJ) — 10-K 2023-02-16, Item 8
- Pfizer Inc (PFE) — 10-K 2025-02-27, Risk Factors
- Eli Lilly and Company (LLY) — 10-K 2026-02-12, Business
- Merck & Co Inc (MRK) — 10-K 2025-02-25, Business

## Comparison vs Claude Sonnet 4.6
- GPT-4o: 819 tokens, 8s, 10 chunks, 4 companies (JNJ/PFE/MRK/LLY) — no AbbVie, no direct quotes, no comparison table, no specific drug names (Keytruda, Eliquis, Januvia)
- Claude: 1,621 tokens, 39s, 18 chunks, 5 companies (JNJ/PFE/MRK/LLY/ABBV) — direct quotes, IRA-specific drug impacts, China VBP/NRDL details, common themes table
- **Critical difference**: GPT-4o was limited to 10 chunks (vs 18) due to OpenAI's per-request TPM ceiling. With equal context, the gap would likely narrow.
- Claude named specific drugs affected by IRA (Keytruda 2028, Januvia 2026, Eliquis) while GPT-4o kept it generic

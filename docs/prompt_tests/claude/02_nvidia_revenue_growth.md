# Test: NVIDIA Revenue & Growth Outlook
**Model:** anthropic/claude-sonnet-4-6
**Date:** 2026-03-13
**Mode:** Verbose
**Latency:** 25,070ms
**Tokens:** 28,446 in / 1,175 out
**Chunks:** 30 retrieved → 18 used

## Question
How has NVIDIA's revenue and growth outlook changed over the last two years?

## Pipeline Details
- **Tickers detected:** NVDA
- **Section hint:** MD&A
- **Retrieval:** Standard single-ticker
- **Where clause:** `{'ticker': 'NVDA'}`

## Model Response

# NVIDIA's Revenue and Growth Outlook: A Two-Year Evolution

## The Revenue Trajectory at a Glance

NVIDIA's revenue has undergone one of the most dramatic transformations in corporate history over the past two-plus years, driven almost entirely by the AI/Data Center boom.

| Fiscal Year / Period | Revenue | YoY Growth |
|---|---|---|
| FY2022 (Jan 2022) | $26.9B | +61% |
| FY2023 (Jan 2023) | $27.0B | ~0% |
| FY2024 (Jan 2024) | $60.9B | +126% |
| FY2025 (Jan 2025) | $130.5B | +114% |
| Q1 FY2025 (Apr 2024) | $26.0B | +262% YoY |
| Q2 FY2025 (Jul 2024) | $30.0B | +122% YoY |
| Q3 FY2026 (Oct 2025) | $57.0B | +62% YoY |

---

## Phase 1: The Trough (FY2023 — Flat Revenue)

- Revenue was essentially **flat at $27.0B** vs. $26.9B in FY2022 [NVDA, 10-K, 2023-02-24]
- **Gaming fell 27%** and **Professional Visualization fell 27%** due to macroeconomic headwinds and channel inventory corrections
- Gross margin **dropped 8 pts to 56.9%** due to $2.17B in inventory charges for excess Ampere architecture products
- Operating income collapsed **58% to $4.2B**, and net income fell **55% to $4.4B**
- Key headwinds: COVID disruptions in China, crypto mining demand collapse, and the $1.35B Arm acquisition termination charge

---

## Phase 2: The AI Explosion (FY2024 — Revenue Doubles)

- Revenue surged **+126% to $60.9B** [NVDA, 10-K, 2024-02-21]
- **Data Center revenue up 217% to $47.5B**, driven by LLM training demand and Hopper GPU ramp; Data Center compute alone rose **244%**
- Gross margin recovered sharply to **72.7%** (+15.8 pts)
- Operating income exploded **+681% to $33.0B**; net income up **+581% to $29.8B**
- "Large cloud providers represented more than half of our Data Center revenue" in Q4 FY2024 [NVDA, 10-K, 2024-02-21]

---

## Phase 3: Continued Hypergrowth (FY2025 — Revenue Doubles Again)

- Full-year FY2025 revenue reached **$130.5B, up 114%** [NVDA, 10-K, 2025-02-26]
- **Compute & Networking segment up 145% to $116.2B**; Data Center compute grew **162%**
- Gross margin improved further to **75.0%**; operating income margin hit **62.4%**
- Three direct customers each represented **11–12% of total revenue** — a new concentration risk [NVDA, 10-K, 2025-02-26]

---

## Phase 4: Growth Moderating but Still Strong (FY2026)

- Q3 FY2026 revenue was **$57.0B, up 62% YoY** — still massive but decelerating from triple-digit growth rates [NVDA, 10-Q, 2025-11-19]
- **Blackwell architecture** is now the leading platform, replacing Hopper; "H20 sales were insignificant in Q3 FY2026"
- Data Center revenue of **$51.2B, up 66% YoY**, driven by "accelerated computing, powerful AI models, and agentic applications"
- A notable headwind: **$4.5B charge** for H20 excess inventory/purchase obligations in Q1 FY2026 [NVDA, 10-Q, 2025-08-27]
- Gross margin dipped slightly to **73.4%** as business transitioned from Hopper HGX to Blackwell full-scale datacenter solutions

---

## Key Takeaway

NVIDIA went from a **near-zero growth company in FY2023** (weighed down by gaming inventory gluts and macro headwinds) to generating **$130B+ in annual revenue by FY2025** — a ~5x increase in two years — almost entirely on the back of AI/Data Center demand. Growth rates are now moderating into the 60% range as the base grows larger, but the Blackwell platform transition signals continued strong demand momentum.

## Sources
- NVIDIA Corporation (NVDA) — 10-K 2024-02-21, Risk Factors
- NVIDIA Corporation (NVDA) — 10-Q 2022-08-31, Risk Factors
- NVIDIA Corporation (NVDA) — 10-Q 2023-08-28, Risk Factors
- NVIDIA Corporation (NVDA) — 10-Q 2022-05-27, Risk Factors
- NVIDIA Corporation (NVDA) — 10-K 2022-03-18, Exhibits, Financial Statement Schedules
- NVIDIA Corporation (NVDA) — 10-K 2023-02-24, ExhibitandFinancial Statement Schedules
- NVIDIA Corporation (NVDA) — 10-Q 2023-05-26, Risk Factors
- NVIDIA Corporation (NVDA) — 10-Q 2024-05-29, Risk Factors
- NVIDIA Corporation (NVDA) — 10-Q 2022-11-18, Risk Factors
- NVIDIA Corporation (NVDA) — 10-K 2022-03-18, Management's Discussion and Analysis
- NVIDIA Corporation (NVDA) — 10-Q 2024-08-28, Risk Factors
- NVIDIA Corporation (NVDA) — 10-K 2025-02-26, Management's Discussion and Analysis
- NVIDIA Corporation (NVDA) — 10-Q 2025-11-19, Risk Factors
- NVIDIA Corporation (NVDA) — 10-Q 2025-08-27, Risk Factors
- NVIDIA Corporation (NVDA) — 10-Q 2023-11-21, Unregistered Sales of Equity Securities

## Verification
**12/12 claims confirmed (100%)**

| Claim | Status |
|---|---|
| FY2022 revenue $26.9B, +61% | CONFIRMED |
| FY2023 revenue flat at $27.0B | CONFIRMED |
| FY2023 Gaming -27%, Data Center +41% | CONFIRMED (computed from end-market breakout) |
| FY2023 gross margin down 8pts to 56.9%, $2.17B inventory charges | CONFIRMED |
| FY2024 revenue $60.9B, +126% | CONFIRMED |
| FY2024 Data Center +217% to $47.5B | CONFIRMED |
| FY2024 gross margin 72.7% | CONFIRMED |
| FY2025 revenue $130.5B, +114% | CONFIRMED |
| Q1 FY2025 revenue $26.04B, +262% | CONFIRMED |
| Q3 FY2026 revenue $57.0B | CONFIRMED |
| $4.5B H20 charge in Q1 FY2026 | CONFIRMED |
| Three direct customers at 11-12% each | CONFIRMED |

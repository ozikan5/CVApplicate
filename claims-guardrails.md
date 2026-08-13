# Claims Guardrails

Constraints on how the material in `master-data.md` may be phrased on your CV.

**These are binding.** `cv-review` and `cv-sanity-check` read this file before editing
`cv.tex` and will not produce a bullet that violates a rule here — even if the resulting
bullet would score higher. A number that impresses a keyword filter but collapses under a
senior engineer's follow-up question is a net loss.

Replace the examples below with your own. Each rule states what is **true**, what may be
**claimed**, and what must **not** be claimed.

---

## Scope-of-metric rules

Numbers that sound broader than they are. State the exact grain the metric was measured at.

### Example: "99% accuracy"

- **True:** 99% F1 on a held-out *pair-classification* set.
- **Claim:** "99% F1 pair classification."
- **Do not claim:** "99% accurate" without qualification — end-to-end accuracy on the
  real task is much lower.

### Example: a latency figure

- **True:** production p50 197ms / p99 829ms.
- **Claim:** the production figures.
- **Do not claim:** local benchmark numbers.

---

## Ownership-verb rules

The difference between a defensible claim and one that unravels in an interview.

| Work | Correct framing |
|---|---|
| *A service you designed and shipped alone* | **Built solo** — claim it fully |
| *An existing system you deployed and hardened* | **Productionized and deployed** — not "designed" or "invented" |
| *One feature inside someone else's platform* | **Feature contribution**, not platform ownership |
| *A team result you contributed to* | **Contributed to** — not "drove" or "delivered" |

---

## Production-status rules

Never describe something as "live" or "in production" above its actual status.

| Work | Actual status |
|---|---|
| *Example service A* | In production |
| *Example service B* | Deployed, but not yet consumed by the live system — say "deployed; integration pending" |
| *Example service C* | Validated in dev, rollout pending — do not call it live |
| *Example project D* | In development |

---

## Attribution rules

Where a result is real but not solely yours, or not yet settled.

- **Early readouts:** if a number comes from a short A/B window or small sample, always
  carry "early readout." Don't present it as a settled result.
- **Team results:** use "contributed to," not "drove," for outcomes multiple people
  produced.
- **Results that went the wrong way:** if something you shipped underperformed, do not
  claim it as a win. Being able to explain what happened and what you're doing about it
  reads as maturity in an interview.

---

## Estimate rules

- Label self-estimates ("saved an estimated ~10 min per ticket") as estimates.
- Prefer a hard adoption or usage signal over an estimated time saving where you have one.
- If AI tooling accelerated the work, own that if asked — it's increasingly a positive
  signal. Don't present velocity figures as if hand-typed solo.

---

## How the review skills apply this

1. They read this file before editing `cv.tex`.
2. When a job description tempts them toward a stronger claim than these rules allow,
   they keep the honest phrasing and report the gap instead. An unmet requirement stated
   plainly is more useful than a bullet that cannot survive an interview.
3. If a fix would require a claim not grounded in `master-data.md`, they report the gap
   rather than inventing it.
4. If your underlying facts change (something ships, an A/B matures), update this file
   first, then the CV.

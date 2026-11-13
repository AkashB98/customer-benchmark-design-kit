# customer-benchmark-design-kit

**A customer speech-to-text benchmark design kit whose centrepiece is everything that happens BEFORE scoring: a contract, a truth-file validation that catches a planted normalization mismatch (WER 24.73% raw vs 8.11% after proper normalization), speaker leakage named by ID, and slice coverage gaps — folded into a refusal gate that produces no scorecard at all until the benchmark is sound.**

When a customer asks "which speech-to-text vendor is better for *our* calls?", the deliverable that decides whether the answer means anything is not the scoring script — it is the benchmark design: which kinds of calls are measured, whose voices, how much of each, under what declared configuration, and against a **truth file** — the human-verified reference transcripts every vendor output is compared against. This kit builds that design phase end to end on synthetic data: a **benchmark contract** — the written agreement declaring slices, sample counts, speakers, vendor configurations and the one text-normalization profile both sides must use — then validation of the truth file against that contract, then config checks on the bundle's own declarations, and only then scoring, behind a gate that refuses to score a benchmark that fails validation. The build was motivated by Applied AI / Applied Data roles (AssemblyAI, Mercor, Figma, Justworks, 2026-11) whose job descriptions centre on designing customer benchmarks, representative datasets, baselines, rubrics and eval frameworks as the pre-sales / evaluation deliverable; it is an original implementation, not a reproduction of any company's process.

> **Synthetic data only.** Every figure is fabricated by a seeded generator for a fictional customer (**Acme Support Co**) and two fictional vendors (**VendorAlpha**, **VendorBeta**). No real company, speaker, call, or transcript is used anywhere, and there is no audio — this kit works on declared text files, by design.

Stdlib-only Python — deliberately. A benchmark a customer will make a buying decision on is an audit artifact: anyone should be able to read every line, re-run it offline, and get byte-identical outputs. Zero network, zero API keys, zero external dependencies.

## The general pattern (WER is the worked instance)

The pattern this kit implements is general, even though only one instance is built: **declare a contract first** (what will be measured, in what slices, at what sample sizes, under what configuration, judged against what reference standard), **validate the reference data against that contract before computing anything** (is it in the declared format, does it cover every declared slice, is any of it contaminated by material a contestant was allowed to practise on), **check configurations as declarations** (the files' stated settings against the contract's, not the data streams), and **only then score — behind a gate that refuses to emit a scorecard when validation failed**, and refuses comparative claims the statistics cannot support. Here the worked instance is speech-to-text, the reference standard is a truth file, contamination is speaker overlap between a tuning set and the eval set, and the score is **WER** — **word error rate** — the edit distance between reference and vendor transcript divided by the reference word count. The generic version is deliberately *not* built; the pattern is documented here so the design transfers, and the code stays specific enough to be testable.

## The planted defects (the headline)

The seeded bundle (`fixtures/defective_bundle.json`, 85 truth rows) plants three defects of exactly the kinds that quietly invalidate real customer benchmarks:

1. **Normalization mismatch.** The truth file was produced under a different **normalization** — the text-cleaning rules (casing, punctuation, number format) applied before comparison — than the contract declares: digits, where the contract requires number words. The bundle's manifest honestly *declares* that wrong profile, so the declaration check catches it before a single word is scored; a stream check corroborates it (all 85 references contain digit tokens). The cost of missing it is printed, not asserted — **WER** computed raw vs after applying the contract profile to both sides:

   | Vendor | WER raw (no normalization) | WER after contract normalization |
   |---|---|---|
   | VendorAlpha | 24.73% | 8.11% |
   | VendorBeta | 32.10% | 16.54% |

   A 15–17 point inflation, from formatting alone, on the defective bundle's utterances.
2. **Speaker-overlap leakage.** **Leakage** — evaluation material a vendor was allowed to tune on, which inflates their score for reasons unrelated to quality. Two eval speakers also appear in the vendor **tuning set** — the speakers a vendor may practise/configure on — and are flagged by name: `SPK-US-SUP-01` and `SPK-GB-SUP-01`.
3. **Slice coverage gaps.** A **slice** — one declared segment of the benchmark, here accent × domain × call type — is missing entirely (`indian/sales`: 0 of 20 required) and another is under-filled (`british/sales`: 5 of 20).

Validation returns exactly 6 issues for the seeded bundle (2× `NORMALIZATION_MISMATCH`, 2× `SPEAKER_LEAKAGE`, 1× `SLICE_MISSING`, 1× `SLICE_UNDERFILLED`), and the refusal gate returns `REFUSED` with `scorecard: None`. There is no way to ask this kit for the defective bundle's scores.

## Quickstart

```bash
# 1. Generate the seeded DEFECTIVE bundle (planted defects, by design)
python3 cli.py generate --out bundle.json

# 2. Or generate the CLEAN bundle (validates, scores)
python3 cli.py generate --clean --out bundle.json

# 3. Contract + config-declaration checks + truth-file validation
python3 cli.py validate --input bundle.json

# 4. The refusal gate + scorecard (exit 1 when REFUSED)
python3 cli.py score --input bundle.json

# 5. Full report: validation + coverage + normalization impact + gate
python3 cli.py report --input bundle.json

# 6. CI gate: exit 0 = validates/scores, 1 = REFUSED (EXPECTED on the
#    seeded defective bundle), 2 = IO / usage error
python3 cli.py check --input bundle.json

# 7. One-command end-to-end demo (refusal leads)
python3 demo.py

# 8. Tiny localhost API: POST /validate /score /report,
#    GET /report, GET /health on 127.0.0.1
python3 cli.py serve --port 8765
```

## The clean benchmark at a glance (seed 42, 120 utterances)

The clean bundle declares 6 slices (accents us_general / british / indian × domains support / sales), 20 utterances each, 5 speakers per slice (30 speakers, each in exactly one slice), 8 disjoint tuning speakers, and a claim floor of 15 utterances per slice.

**Overall:** VendorAlpha **WER 8.63%**, **CER** — **character error rate** — the same edit-distance ratio at character level — **8.61%**; VendorBeta **WER 16.80%**, CER **16.05%**.

**Per-slice winner claims** come from a **paired bootstrap CI** — a **confidence interval** built by resampling whole utterances (both vendors' transcripts together, so the comparison stays paired), 1,000 seeded resamples, on the per-utterance WER difference (Alpha − Beta). The gate allows a "Vendor X wins this slice" claim only when the CI excludes 0 **and** the slice meets the claim floor:

| Slice | Alpha WER | Beta WER | Mean diff | 95% CI | Claim |
|---|---|---|---|---|---|
| us_general/support | 6.84% | 15.89% | −0.0906 | [−0.1542, −0.0317] | VendorAlpha wins |
| us_general/sales | 7.44% | 17.56% | −0.1012 | [−0.1488, −0.0542] | VendorAlpha wins |
| british/support | 9.61% | 13.98% | −0.0437 | [−0.1009, +0.0090] | **No claim — CI crosses 0** |
| british/sales | 9.95% | 12.27% | −0.0232 | [−0.0747, +0.0302] | **No claim — CI crosses 0** |
| indian/support | 7.19% | 18.53% | −0.1133 | [−0.1750, −0.0558] | VendorAlpha wins |
| indian/sales | 10.73% | 22.56% | −0.1184 | [−0.2142, −0.0346] | VendorAlpha wins |

On british speech the vendors are closer, and at n=20 per slice the honest answer is "not resolved at this sample size" — the kit says exactly that instead of crowning a winner on a point estimate. The floor rule is exercised separately (eval E14): a valid bundle with a slice at n=10 still scores, but that slice gets no winner claim.

## How it works

**The contract.** `contract.py` validates the declaration itself (exactly two vendors — a paired comparison needs a pair; a complete normalization profile; positive minimums; no speaker declared in two slices) and checks a bundle manifest's declared sample rate, language and per-file normalization profiles against it. Those are declaration checks: they read what the files *claim* to be, which is where a mismatched truth file is cheapest to catch.

**Validation before scoring.** `validation.py` runs after the contract checks and before any error rate exists: manifest-vs-contract mismatches, truth-file field/duplicate checks, declared-vs-actual slice coverage, speaker overlap between the tuning declaration and the eval speakers (named), digit-token corroboration of a normalization mismatch, and hypothesis files covering exactly the truth IDs per vendor. It reports issues and never raises on bad data, so `check` can map refusal to exit 1, distinct from an IO/data error (exit 2).

**Scoring.** Word-level WER and character-level CER only, both sides normalized under the single contract profile first. Nothing else is scored: no diarization error rate, no speaker attribution, no audio handling — a benchmark kit that claims only what it measures.

**The gate.** `scorecard.py` folds the scorecard into the refusal gate: one function validates, and either returns `REFUSED` with reasons and no scores, or the full scorecard with per-slice/overall WER + CER, the paired bootstrap CI per slice, and the claim decision per slice with its reason.

## Architecture

| Module | Job |
|---|---|
| `contract.py` | Contract validation (slices, counts, speakers, two vendors, normalization profile, claim floor) + manifest config-declaration checks (sample rate, language, declared normalizations) |
| `normalize.py` | The one normalization implementation: lowercase, punctuation stripping, digit-token → number-word expansion, driven by the declared profile |
| `generator.py` | Deterministic synthetic bundles: fictional Acme contract, template transcripts per domain, seeded per-vendor/per-accent corruption; clean flavour + defective flavour with the three planted defects; JSON serialiser/loader |
| `validation.py` | Truth-file validation before scoring: normalization/config mismatches, slice coverage, named speaker leakage, duplicates, hypothesis coverage — reports issues, never raises on bad data |
| `scoring.py` | WER and CER (edit distance at word / character level), per-utterance errors, raw-vs-normalized WER impact, seeded paired bootstrap CI (stdlib) |
| `scorecard.py` | The refusal gate + scorecard (folded together) and the full report assembly (validation, coverage, normalization impact, gate, scorecard) |
| `cli.py` | `generate` / `validate` / `score` / `report` / `check` (CI exit 0/1/2) / `demo` / `serve` (stdlib `http.server` on 127.0.0.1: `POST /validate`, `POST /score`, `POST /report`, `GET /report`, `GET /health`) |
| `demo.py` | End-to-end narrative with asserts, led by the refusal: determinism, all planted defects caught, normalization before/after, REFUSED gate, clean scorecard + claims, check exit codes (1 defective by design, 0 clean, 2 missing file), live localhost serve round-trip |
| `fixtures/` | Both seeded bundles (`clean_bundle.json`: 120 truth rows; `defective_bundle.json`: 85 truth rows) with pinned hashes |

## Evals

`python3 evals/run_evals.py` → **15/15 golden evals**, report committed at `evals/eval_report.json` (md5 `12592b466dba2e54b22b100dd4277741`, byte-identical across 3 verified runs):

- **E1** generator determinism — both bundle flavours pinned by md5 (clean `b9d1ea1b6c1aeb19d2d64c554472c794`, defective `85e93c0d480c466e40271ba4687669be`)
- **E2** truth counts pinned (clean 120, defective 85)
- **E3** defective validation pinned — exactly 6 issues by code; clean bundle validates with none
- **E4** leakage speakers pinned (`SPK-US-SUP-01`, `SPK-GB-SUP-01`)
- **E5** coverage pinned (indian/sales 0/20, british/sales 5/20, all other slices full)
- **E6** normalization impact pinned (Alpha 24.73% raw → 8.11% normalized; Beta 32.10% → 16.54%)
- **E7** refusal gate pinned (REFUSED, scorecard None, 6 reasons)
- **E8** clean scorecard pinned (Alpha WER 8.63% / CER 8.61%; Beta WER 16.80% / CER 16.05%)
- **E9** claims pinned (VendorAlpha wins 4 slices; both british slices no claim, CI crosses 0)
- **E10** paired bootstrap pinned (us_general/support: mean diff −0.0906, CI [−0.1542, −0.0317], n=20, 1,000 reps)
- **E11** WER/CER hand-computed (substitution 1/3, deletion 1/4, CER 1/3)
- **E12** CLI `check` exit codes 1 / 0 / 2 (the seeded 1 is the planted defects, by design)
- **E13** serve round-trip matches local scorecard + report exactly
- **E14** claim floor — valid bundle, slice at n=10: scores, but winner is None with the floor reason
- **E15** bundled fixtures pinned (clean validates with identical scorecard; defective refused)

Unit tests: `python3 -m unittest discover -s tests` → **41 hermetic tests**, including a no-network enforcement test (sockets stubbed), hand-computed WER/CER/bootstrap fixtures, the floor-bundle claim refusal, leakage naming, config-mismatch detection, CLI exit codes, and serve round-trips.

## Development loop — what the checks actually caught

1. **The first speaker assignment violated the kit's own contract.** The generator initially gave each accent one pool of 5 speakers shared by its support and sales slices — while the contract validator (correctly) forbids a speaker appearing in two slices, since a shared speaker blurs the per-slice readouts the benchmark exists to produce. The demo failed on the *clean* bundle before any scoring happened: 15 "declared in two slices" issues. Fix: speakers are now unique per slice (30 speakers, IDs carry the slice's domain tag, e.g. `SPK-US-SUP-01` vs `SPK-US-SAL-01`), and a unit test pins the one-slice-per-speaker invariant. The validator was right; the generator was wrong — which is the relationship this kit is built to have with its users' data, too.

## Scope and honest limits

- **STT / text WER only.** The worked instance is speech-to-text scored at word and character level. There is no audio handling, no diarization error rate, no speaker-attribution scoring, and no other error-rate variants — extending the pattern to another task means writing that task's contract and scorer, not flipping a flag here.
- **Synthetic vendor behaviour is a caricature.** Vendor errors are seeded word substitutions/deletions/insertions at per-accent rates chosen so the statistics have something to resolve (and, on british slices, something they honestly cannot). Real STT errors are acoustic, correlated within a call, and nothing like this generator.
- **The normalization check trusts declarations, then corroborates.** The primary catch is the manifest declaring a profile that differs from the contract — a real engagement would need the same honesty (or a format audit) from whoever produced the truth file. The digit-token stream check corroborates this one planted form; a subtler mismatch (number words vs digits is visible; a punctuation-only difference would be partly invisible after stripping) could pass, and the kit does not claim otherwise.
- **The bootstrap is per-utterance, not per-speaker or per-call.** Resampling utterances treats them as independent; utterances from one speaker are not. A production benchmark should cluster the resample at speaker or call level — the claim floor and the CI-crossing refusals are the kit's acknowledgement that n=20 slices are small, not a solution to clustering.
- **Coverage is counts, not representativeness.** A slice can hit its 20-utterance minimum with unrepresentative calls and pass. The contract declares *what* representative means only as far as accent/domain/call-type; auditing real-world fit is a human design review this kit supports but does not automate.
- **The API is a demo surface.** It binds 127.0.0.1 only, holds its bundle in memory, and resets on restart.

## Why this project

It takes the author's target craft — forward-deployed evaluation work with customers — and rebuilds its least glamorous, most decisive phase as an engineering artifact: the benchmark contract a customer signs off on before anyone scores anything, the validation that catches the three ways such benchmarks quietly lie (a mismatched truth file, leaked speakers, missing slices), and a gate with the discipline to print REFUSED instead of a precise-looking, meaningless number. Declare the contract, validate before scoring, refuse what fails, and only claim what the interval supports.

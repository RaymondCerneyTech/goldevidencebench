# Measurements Archive

Move older or superseded experiment writeups here to keep `MEASUREMENTS.md` focused and readable.

## Archived: v2/v3 notes (moved from MEASUREMENTS.md)

## v2 release notes
- Defaults to closed-book evaluation and supports richer state modes + derived queries.
- Added authority-aware selection (`GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER=1`) to fix kv_commentary NOTE noise.
- Verified perfect end-to-end exact_acc (citations on) for kv_commentary using the reference system (Qwen 2.5 7B Q5_K_M, retrieval_llama_cpp_adapter, authority filter on; s3q16 + s5q24 grids, k=2/4/8). (see runs/*authfilter*; command below).
- Added compute vs quality figure and multi-model kv comparison.

## V2 takeaway (authority-aware selection)

In kv_commentary, the dominant failure is *authoritativeness*, not selection or attribution. Adding `GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER=1` (drop NOTE lines before selection) restores perfect end-to-end accuracy in the kv_commentary grids (s3q16 + s5q24, k=2/4/8) for the reference system (Qwen 2.5 7B Q5_K_M, retrieval_llama_cpp_adapter). This is now the recommended default for kv_commentary.
Runs: `runs/kv_commentary_grid_linear_authfilter_k{2,4,8}_s3q16` and `runs/kv_commentary_grid_linear_authfilter_k{2,4,8}_s5q24`.
Clean authority-filter A/B (kv_commentary, s3q16, gold present = 1.0):

| rerank | k | value_acc | exact_acc | selection_rate |
| --- | --- | --- | --- | --- |
| prefer_set_latest | 2 | 0.9375 | 0.9375 | 0.9375 |
| prefer_set_latest | 4 | 0.9375 | 0.9375 | 0.9375 |
| prefer_set_latest | 8 | 0.9375 | 0.9375 | 0.9375 |
| linear | 2 | 1.0000 | 1.0000 | 1.0000 |
| linear | 4 | 1.0000 | 1.0000 | 1.0000 |
| linear | 8 | 1.0000 | 1.0000 | 1.0000 |

Clean authority-filter A/B (kv_commentary, s5q24, gold present = 1.0):

| rerank | k | value_acc | exact_acc | selection_rate |
| --- | --- | --- | --- | --- |
| prefer_set_latest | 2 | 0.8917 | 0.8917 | 0.8917 |
| prefer_set_latest | 4 | 0.8917 | 0.8917 | 0.8917 |
| prefer_set_latest | 8 | 0.8917 | 0.8917 | 0.8917 |
| linear | 2 | 1.0000 | 1.0000 | 1.0000 |
| linear | 4 | 1.0000 | 1.0000 | 1.0000 |
| linear | 8 | 1.0000 | 1.0000 | 1.0000 |


Command (s3q16 example):

```powershell
$env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER = "1"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = "linear"
foreach ($k in 2,4,8) {
  $env:GOLDEVIDENCEBENCH_RETRIEVAL_K = "$k"
  $outDir = "runs\kv_commentary_grid_linear_authfilter_k${k}_s3q16"
  goldevidencebench sweep --out $outDir --seeds 3 --episodes 1 --steps 240 --queries 16 `
    --state-modes kv_commentary --distractor-profiles standard `
    --adapter goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter --no-derived-queries `
    --no-twins --require-citations --results-json "$outDir\combined.json" `
    --max-book-tokens 400 --note-rate 0.30
  python .\scripts\summarize_results.py --in "$outDir\combined.json" --out-json "$outDir\summary.json"
}
```
Canonical v2 default: authority filter (hard gate) + `prefer_update_latest` (soft tie-break).

## V3 plan (NOTE robustness + authority spoofing)

**V3-D: UPDATE-vs-UPDATE disambiguation + abstain**

Matrix (filter ON/OFF ? spoof_rate ? k):

```powershell
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = "linear"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_LINEAR_MODEL = ".\models\linear_selector_note_v8.json"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_SPOOF_SEED = "0"

foreach ($filter in @('0','1')) {
  if ($filter -eq '1') { $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER = '1' } else { Remove-Item Env:\GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER -ErrorAction SilentlyContinue }
  foreach ($spoof in 0.1,0.5,0.8) {
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_SPOOF_RATE = "$spoof"
    foreach ($k in 2,4,8) {
      $env:GOLDEVIDENCEBENCH_RETRIEVAL_K = "$k"
      $outDir = "runs\v3d_spoof${spoof}_filter${filter}_k${k}_s3q16"
      goldevidencebench sweep --out $outDir --seeds 3 --episodes 1 --steps 240 --queries 16 `
        --state-modes kv_commentary --distractor-profiles standard `
        --adapter goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter --no-derived-queries `
        --no-twins --require-citations --results-json "$outDir\combined.json" `
        --max-book-tokens 400 --note-rate 0.30
      python .\scripts\summarize_results.py --in "$outDir\combined.json" --out-json "$outDir\summary.json"
    }
  }
}
```

Report: wrong_update_rate, spoof_accept_rate_non_gold, value_acc, and abstain precision/recall (if enabled).

Abstain calibration (drop sweep example, k=4):

```powershell
$env:GOLDEVIDENCEBENCH_RETRIEVAL_ABSTAIN_ON_MISSING = "1"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_DROP_SEED = "0"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = "linear"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_K = "4"
foreach ($drop in 0.0,0.2,0.4) {
  $env:GOLDEVIDENCEBENCH_RETRIEVAL_DROP_PROB = "$drop"
  $outDir = "runs\abstain_drop${drop}_k4_s3q16"
  goldevidencebench sweep --out $outDir --seeds 3 --episodes 1 --steps 240 --queries 16 `
    --state-modes kv_commentary --distractor-profiles standard `
    --adapter goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter --no-derived-queries `
    --no-twins --require-citations --results-json "$outDir\combined.json" `
    --max-book-tokens 400 --note-rate 0.30
  python .\scripts\summarize_results.py --in "$outDir\combined.json" --out-json "$outDir\summary.json"
}
```

Use `summary.json` (or `runs/summary_all.csv`) to read `abstain_precision` and `abstain_recall`.

V3-D matrix summary (v8 selector, s3q16):

| filter | spoof_rate | k | value_acc | selected_note_rate | wrong_update_rate | spoof_accept_rate_non_gold |
| --- | --- | --- | --- | --- | --- | --- |
| off | 0.1 | 2/4/8 | 0.6875 | 0.3125 | 0.0000 | 0.0000 |
| off | 0.5 | 2/4/8 | 0.6875 | 0.3125 | 0.0000 | 0.0000 |
| off | 0.8 | 2/4/8 | 0.6875 | 0.3125 | 0.0000 | 0.0000 |
| on | 0.1 | 2/4/8 | 1.0000 | 0.0000 | 0.0000 | 0.0000 |
| on | 0.5 | 2/4/8 | 1.0000 | 0.0000 | 0.0000 | 0.0000 |
| on | 0.8 | 2/4/8 | 1.0000 | 0.0000 | 0.0000 | 0.0000 |

Interpretation: spoof exposure rises with spoof_rate/k, but spoofed non-gold selections stay at 0.0; filter OFF fails only via NOTE authority violations, while filter ON is perfect across the grid.

Runs: runs/v3d_spoof{0.1,0.5,0.8}_filter{0,1}_k{2,4,8}_s3q16 (18 runs total).



**V3-A: Learned NOTE robustness (trusted authority field)**

Train with NOTE candidates present, but label the gold UPDATE as correct using `export_selector_dataset.py --use-gold-support` so the selector learns authority, not just recency.

- Train selector with NOTES present.
- Evaluate with the authority filter OFF.
- Authority is a structured feature (not just text pattern).
- Goal: match linear baseline behavior without hard gating.

**V3-B: Authority spoofing (untrusted authority signal)**

- Add a stress profile where some NOTE lines look like UPDATEs, or UPDATE lines contain NOTE text, or the authority marker is missing/ambiguous.
- Measure how often the selector is tricked and whether abstain triggers when authority is unclear.
- Report spoof_accept_rate + gold_support_selected_rate.

Command (s3q16 example, spoof cues at 30%):

```powershell
Remove-Item Env:\GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER -ErrorAction SilentlyContinue
$env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_SPOOF_RATE = "0.3"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_SPOOF_SEED = "0"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = "linear"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_K = "4"
$outDir = "runs\authority_spoof_0.3_linear_k4_s3q16"
goldevidencebench sweep --out $outDir --seeds 3 --episodes 1 --steps 240 --queries 16 `
  --state-modes kv_commentary --distractor-profiles standard `
  --adapter goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter --no-derived-queries `
  --no-twins --require-citations --results-json "$outDir\combined.json" `
  --max-book-tokens 400 --note-rate 0.30
python .\scripts\summarize_results.py --in "$outDir\combined.json" --out-json "$outDir\summary.json"
```
UPDATE burst stress test (new distractor profile):

`update_burst` injects rapid same-key UPDATE bursts with near-miss values so the latest update is easy to confuse with the previous one. This stresses wrong-UPDATE selection.

Optional: set `GOLDEVIDENCEBENCH_UPDATE_BURST_RATE` (or `--update-burst-rate`) to control burst probability; default is 0.25.

```powershell
$outDir = "runs\update_burst_k4_s3q16"
goldevidencebench sweep --out $outDir --seeds 3 --episodes 1 --steps 240 --queries 16 `
  --state-modes kv --distractor-profiles update_burst `
  --adapter goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter --no-derived-queries `
  --no-twins --require-citations --results-json "$outDir\combined.json" `
  --max-book-tokens 400
python .\scripts\summarize_results.py --in "$outDir\combined.json" --out-json "$outDir\summary.json"
```


Update-burst rate sweep (k=4, steps=240, s5q24; gold_present_rate=1.0):

| burst_rate | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- |
| 0.10 | 0.9500 | 0.0500 | 0.9500 |
| 0.25 | 0.9000 | 0.1000 | 0.9000 |
| 0.40 | 0.7833 | 0.2167 | 0.7833 |

Runs: runs/update_burst_rate0.10_k4_steps240_s5q24, runs/update_burst_rate0.25_k4_steps240_s5q24, runs/update_burst_rate0.40_k4_steps240_s5q24.

Interpretation: higher burst density increases wrong-UPDATE selection and lowers accuracy; this trend is clearer with s5q24 than the smaller s3q16 checks.

Negative result (update_burst training, k=8, rate=0.40, s5q24):

| selector | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- |
| baseline linear | 0.8917 | 0.1083 | 0.8917 |
| update_burst-trained | 0.8250 | 0.1750 | 0.8250 |

Runs: runs/update_burst_linear_baseline_k8_rate0.40_s5q24, runs/update_burst_linear_updatebursttrain_k8_rate0.40_s5q24.

Interpretation: hard-negative training on update_burst did not improve wrong-UPDATE selection; it degraded performance in this regime.

Optional linear tie-breaker A/B (k=8, rate=0.40, s5q24; gold_present_rate=1.0):

| tie_break | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- |
| none | 0.7583 | 0.2417 | 0.7583 |
| latest_step | 0.8417 | 0.1583 | 0.8417 |

Runs: runs/update_burst_linear_tienone_k8_rate0.40_s5q24, runs/update_burst_linear_tielatest_step_k8_rate0.40_s5q24.

Interpretation: in the hardest regime (k=8, rate=0.40), recency tie-breaking materially improves wrong-UPDATE selection.
Wall cutoff (k=8, s5q24): rate=0.33 holds (value_acc=0.9250, wrong_update_rate=0.0750), rate=0.34 drops (value_acc=0.8500, wrong_update_rate=0.1500). Runs: runs/update_burst_linear_k8_rate0.33_s5q24, runs/update_burst_linear_k8_rate0.34_s5q24.

Selector-only wall map (k=8, s5q24; gold_present_rate=1.0):

| rate | rerank | selection_rate | wrong_update_rate |
| --- | --- | --- | --- |
| 0.25 | none | 0.2500 | 0.7500 |
| 0.25 | linear | 0.8583 | 0.1417 |
| 0.25 | latest_step | 1.0000 | 0.0000 |
| 0.30 | none | 0.1667 | 0.8333 |
| 0.30 | linear | 0.9250 | 0.0750 |
| 0.30 | latest_step | 1.0000 | 0.0000 |
| 0.35 | none | 0.0417 | 0.9583 |
| 0.35 | linear | 0.9000 | 0.1000 |
| 0.35 | latest_step | 1.0000 | 0.0000 |
| 0.40 | none | 0.1250 | 0.8750 |
| 0.40 | linear | 0.8333 | 0.1667 |
| 0.40 | latest_step | 1.0000 | 0.0000 |

Runs: runs/update_burst_selonly_none_k8_rate0.25_s5q24, runs/update_burst_selonly_linear_k8_rate0.25_s5q24, runs/update_burst_selonly_latest_step_k8_rate0.25_s5q24,
      runs/update_burst_selonly_none_k8_rate0.30_s5q24, runs/update_burst_selonly_linear_k8_rate0.30_s5q24, runs/update_burst_selonly_latest_step_k8_rate0.30_s5q24,
      runs/update_burst_selonly_none_k8_rate0.35_s5q24, runs/update_burst_selonly_linear_k8_rate0.35_s5q24, runs/update_burst_selonly_latest_step_k8_rate0.35_s5q24,
      runs/update_burst_selonly_none_k8_rate0.40_s5q24, runs/update_burst_selonly_linear_k8_rate0.40_s5q24, runs/update_burst_selonly_latest_step_k8_rate0.40_s5q24.

Interpretation: in selector-only mode, latest_step fully resolves wrong-UPDATE selection under update_burst; linear helps but does not saturate.



Selector-only update_burst (k=8, s3q16, linear):

| rate | selection_rate | wrong_update_rate |
| --- | --- | --- |
| 0.30 | 1.0000 | 0.0000 |
| 0.40 | 1.0000 | 0.0000 |
| 0.50 | 1.0000 | 0.0000 |

Runs: runs/update_burst_linear_k8_rate0.30_s3q16, runs/update_burst_linear_k8_rate0.40_s3q16, runs/update_burst_linear_k8_rate0.50_s3q16.

Interpretation: at the smaller s3q16 setting, linear selection saturates even at high burst rates; the hard regime appears in the larger s5q24 setting and in full-pipeline runs.

Full pipeline update_burst (k=8, rate=0.40, s3q16; gold_present_rate=1.0):

| copy_clamp | selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc |
| --- | --- | --- | --- | --- |
| 0 | 0.6875 | 0.3125 | 0.0625 | 0.0625 |
| 1 | 0.2500 | 0.7500 | 0.0625 | 0.0625 |

Runs: runs/update_burst_full_linear_copy0_k8_rate0.40_s3q16, runs/update_burst_full_linear_copy1_k8_rate0.40_s3q16.

Interpretation: copy-clamp does not fix update_burst in the full pipeline; selection collapses when clamp=1 and wrong-UPDATE selection dominates either way. Keep clamp off for update_burst; the linear tie-break below also underperforms in this regime, so focus on stronger UPDATE disambiguation features.

Full pipeline update_burst with linear tie-break (k=8, rate=0.40, s3q16; gold_present_rate=1.0):

| selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc |
| --- | --- | --- | --- |
| 0.4167 | 0.5833 | 0.1250 | 0.1250 |

Run: runs/update_burst_full_linear_tie_k8_rate0.40_s3q16.

Interpretation: the tie-breaker underperforms the baseline in this full-pipeline setting (lower selection_rate, higher wrong_update_rate). It is not a safe default here.

Full pipeline update_burst with prefer_update_latest (k=8, rate=0.40, s3q16; gold_present_rate=1.0):

| selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc |
| --- | --- | --- | --- |
| 0.6250 | 0.3750 | 0.1250 | 0.1250 |

Run: runs/update_burst_full_prefer_update_latest_k8_rate0.40_s3q16.

Interpretation: prefer_update_latest improves selection vs tie-break, but still leaves substantial wrong-UPDATE errors and low value accuracy. The bottleneck remains UPDATE disambiguation and answer extraction.

Full pipeline update_burst with prefer_update_latest + copy-clamp (k=8, rate=0.40, s3q16; gold_present_rate=1.0):

| selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc |
| --- | --- | --- | --- |
| 0.4375 | 0.5625 | 0.1250 | 0.1250 |

Run: runs/update_burst_full_prefer_update_latest_copy1_k8_rate0.40_s3q16.

Interpretation: copy-clamp does not improve prefer_update_latest in the update_burst full pipeline; selection drops and wrong-UPDATE errors dominate. Treat copy-clamp as unsafe in this regime.

Full pipeline update_burst A/B (k=8, s3q16; gold_present_rate=1.0):

| burst_rate | rerank | selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc |
| --- | --- | --- | --- | --- | --- |
| 0.25 | linear | 0.7083 | 0.2917 | 0.0417 | 0.0417 |
| 0.25 | prefer_update_latest | 0.6250 | 0.3750 | 0.0417 | 0.0417 |
| 0.30 | linear | 0.6250 | 0.3750 | 0.1458 | 0.1458 |
| 0.30 | prefer_update_latest | 0.5000 | 0.5000 | 0.1458 | 0.1458 |
| 0.35 | linear | 0.6667 | 0.3333 | 0.0833 | 0.0833 |
| 0.35 | prefer_update_latest | 0.5000 | 0.5000 | 0.0833 | 0.0833 |

Runs: runs/update_burst_full_linear_k8_rate0.25_s3q16, runs/update_burst_full_prefer_update_latest_k8_rate0.25_s3q16, runs/update_burst_full_linear_k8_rate0.30_s3q16, runs/update_burst_full_prefer_update_latest_k8_rate0.30_s3q16, runs/update_burst_full_linear_k8_rate0.35_s3q16, runs/update_burst_full_prefer_update_latest_k8_rate0.35_s3q16.

Interpretation: linear beats prefer_update_latest on selection rate at 0.25 and 0.35, but accuracy_when_gold_present is very low across these runs, so answerer/extraction dominates. If this is unexpected, double-check that no answerer clamps or deterministic modes were left on in the environment.

Deterministic answerer check (k=8, s3q16; gold_present_rate=1.0):

| burst_rate | rerank | selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc | answer_acc_given_gold_selected |
| --- | --- | --- | --- | --- | --- | --- |
| 0.25 | linear | 0.5208 | 0.4792 | 0.0417 | 0.0417 | 0.0400 |
| 0.25 | prefer_update_latest | 0.5000 | 0.5000 | 0.0417 | 0.0417 | 0.0833 |
| 0.35 | linear | 0.2917 | 0.7083 | 0.0833 | 0.0833 | 0.1429 |
| 0.35 | prefer_update_latest | 0.4375 | 0.5625 | 0.0833 | 0.0833 | 0.0000 |

Runs: runs/update_burst_full_linear_detanswer_k8_rate0.25_s3q16, runs/update_burst_full_prefer_update_latest_detanswer_k8_rate0.25_s3q16, runs/update_burst_full_linear_detanswer_k8_rate0.35_s3q16, runs/update_burst_full_prefer_update_latest_detanswer_k8_rate0.35_s3q16.

Interpretation: deterministic answer did not lift accuracy_when_gold_present; answer_acc_given_gold_selected is still low. That means the deterministic path is either not active in this regime or the selected lines are not parse-stable. Treat this as a diagnostic (validate the env var and parsing rules before interpreting it as a model failure).

Clean sanity check (kv, s1q4, deterministic answerer, clean env): value_acc=1.0, selection_rate=1.0, answer_acc_given_gold_selected=1.0.
Run: runs/detanswer_sanity_kv_s1q4_clean.

Clean update_burst deterministic answerer (k=8, s3q16; clean env):

| rerank | burst_rate | selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc | answer_acc_given_gold_selected |
| --- | --- | --- | --- | --- | --- | --- |
| linear | 0.25 | 0.9167 | 0.0833 | 0.9167 | 0.9167 | 1.0000 |
| linear | 0.35 | 0.8750 | 0.1250 | 0.8750 | 0.8750 | 1.0000 |
| prefer_update_latest | 0.25 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |
| prefer_update_latest | 0.35 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |

Runs: runs/update_burst_full_linear_detanswer_k8_rate0.25_s3q16_clean, runs/update_burst_full_linear_detanswer_k8_rate0.35_s3q16_clean, runs/update_burst_full_prefer_update_latest_detanswer_k8_rate0.25_s3q16_clean, runs/update_burst_full_prefer_update_latest_detanswer_k8_rate0.35_s3q16_clean.

Interpretation: with a clean env, deterministic answerer works (answer_acc_given_gold_selected=1.0). Remaining error is selection; prefer_update_latest resolves wrong-update picks in this regime.

Environment hygiene (when to clean):

- Before any deterministic answerer diagnostic (to avoid stale clamps/flags masking results).
- After switching state mode, distractor profile, or reranker model.
- After toggling any retrieval/answerer flags (authority filter, copy-clamp, deterministic answer, abstain, drop_prob, k).
- If results look inconsistent with known baselines.

Clean env command (PowerShell):

```powershell
Remove-Item Env:\GOLDEVIDENCEBENCH_* -ErrorAction SilentlyContinue
```

Selector-only update_burst A/B (k=8, rate=0.40, s3q16; gold_present_rate=1.0):

| rerank | selection_rate | wrong_update_rate | accuracy_when_gold_present | value_acc |
| --- | --- | --- | --- | --- |
| linear | 0.3750 | 0.6250 | 0.1250 | 0.1250 |
| prefer_update_latest | 0.6250 | 0.3750 | 0.1250 | 0.1250 |

Runs: runs/update_burst_selonly_linear_k8_rate0.40_s3q16, runs/update_burst_selonly_prefer_update_latest_k8_rate0.40_s3q16.

Interpretation: even in selector-only mode, prefer_update_latest materially outperforms linear on UPDATE disambiguation. The remaining error is selection (wrong-UPDATE) rather than answer extraction.







Abstain calibration (selection-only, update_burst k=8 rate=0.34, s3q16):

| drop_prob | abstain_rate | abstain_precision | abstain_recall | selection_rate | wrong_update_rate |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 0.0000 | ? | ? | 0.8750 | 0.1250 |
| 0.2 | 0.1579 | 1.0000 | 1.0000 | 0.7292 | 0.1026 |
| 0.4 | 0.2727 | 1.0000 | 1.0000 | 0.5417 | 0.1333 |

Runs: runs/abstain_update_burst_k8_rate0.34_drop{0,0.2,0.4}_s3q16.

Interpretation: abstain triggers only when the gold line is dropped from candidates, with perfect precision/recall in this sweep; baseline (drop=0) does not abstain.

Full pipeline abstain calibration (update_burst k=8 rate=0.34, s3q16):

| drop_prob | value_acc | abstain_rate | abstain_precision | abstain_recall | selection_rate | wrong_update_rate |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0 | 0.9167 | 0.0000 | ? | ? | 0.9167 | 0.0833 |
| 0.2 | 0.5208 | 0.3043 | 1.0000 | 1.0000 | 0.4792 | 0.1481 |
| 0.4 | 0.6042 | 0.2727 | 1.0000 | 1.0000 | 0.5625 | 0.1000 |

Runs: runs/abstain_update_burst_k8_rate0.34_drop{0,0.2,0.4}_s3q16_full.

Interpretation: abstain remains perfectly calibrated end-to-end; accuracy drops as expected when gold is removed from the candidate set.




Negative result (recency_v2 feature, k=8, s5q24; gold_present_rate=1.0):

| rate | selector | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- | --- |
| 0.35 | baseline linear | 0.8917 | 0.1083 | 0.8917 |
| 0.35 | recency_v2 | 0.8333 | 0.1667 | 0.8333 |
| 0.40 | baseline linear | 0.8000 | 0.2000 | 0.8000 |
| 0.40 | recency_v2 | 0.6667 | 0.3333 | 0.6667 |

Runs: runs/update_burst_linear_baseline_k8_rate0.35_s5q24, runs/update_burst_linear_recency_v2_k8_rate0.35_s5q24,
      runs/update_burst_linear_baseline_k8_rate0.40_s5q24, runs/update_burst_linear_recency_v2_k8_rate0.40_s5q24.

Interpretation: the added recency_v2 feature regresses wrong-UPDATE selection at high burst rates; keep the tie-breaker, avoid this training tweak.

Negative result (recency-rank retrain v9, k=8, s5q24; gold_present_rate=1.0):

| rate | selector | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- | --- |
| 0.33 | baseline linear | 0.9250 | 0.0750 | 0.9250 |
| 0.33 | recency_rank_v9 | 0.2917 | 0.7083 | 0.2917 |
| 0.34 | baseline linear | 0.8500 | 0.1500 | 0.8500 |
| 0.34 | recency_rank_v9 | 0.2500 | 0.7500 | 0.2500 |

Runs: runs/update_burst_linear_k8_rate0.33_s5q24, runs/update_burst_linear_k8_rate0.34_s5q24,
      runs/update_burst_linear_v9_k8_rate0.33_s5q24, runs/update_burst_linear_v9_k8_rate0.34_s5q24.

Interpretation: the recency-rank feature retrain collapsed under update_burst; do not use v9 weights.

Negative result (recency-rank retrain v9b, low LR + wrong-update penalty, k=8, s5q24; gold_present_rate=1.0):

| rate | selector | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- | --- |
| 0.33 | baseline linear | 0.9250 | 0.0750 | 0.9250 |
| 0.33 | recency_rank_v9b | 0.0833 | 0.9167 | 0.0917 |
| 0.34 | baseline linear | 0.8500 | 0.1500 | 0.8500 |
| 0.34 | recency_rank_v9b | 0.1500 | 0.8500 | 0.1500 |

Runs: runs/update_burst_linear_k8_rate0.33_s5q24, runs/update_burst_linear_k8_rate0.34_s5q24,
      runs/update_burst_linear_v9b_k8_rate0.33_s5q24, runs/update_burst_linear_v9b_k8_rate0.34_s5q24.

Interpretation: low-LR + wrong-update penalty retrain made wrong-UPDATE selection much worse; avoid v9b.






V3-B authority spoofing results (s3q16, k=4, gold_present_rate = 1.0):

| spoof_rate | value_acc | selection_rate | gold_support_selected_rate | selected_note_rate | wrong_update_rate | spoof_accept_rate |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 0.7708 | 0.6042 | 0.7708 | 0.0833 | 0.1458 | 0.0833 |
| 0.5 | 0.4375 | 0.4375 | 0.4375 | 0.2500 | 0.3125 | 0.2708 |

Runs: runs/authority_spoof_0.1_linear_k4_s3q16, runs/authority_spoof_0.5_linear_k4_s3q16.

Interpretation: higher spoofing raises spoof_accept_rate and wrong_update_rate, and accuracy tracks the resulting selection collapse.

V3-B spoof filter A/B (prefer_update_latest, spoof_rate=0.5, s3q16, k=4):

| authority_filter | value_acc | selection_rate | gold_support_selected_rate | selected_note_rate | wrong_update_rate | spoof_accept_rate |
| --- | --- | --- | --- | --- | --- | --- |
| off | 0.2708 | 0.4167 | 0.2708 | 0.3750 | 0.3542 | 0.3958 |
| on | 0.3125 | 0.3125 | 0.3125 | 0.0000 | 0.6875 | 0.0625 |

Interpretation: the filter eliminates NOTE picks and sharply lowers spoof acceptance; remaining errors are almost entirely wrong UPDATE selection.

Takeaway: with spoofing, authority filtering solves NOTE/spoof confusion but exposes the next bottleneck (wrong UPDATE selection).

NOTE camouflage stress test (new distractor profile):

`note_camouflage` makes NOTE lines look like updates (e.g., "UPDATE: SET ..." or quoted UPDATEs) while keeping them non-authoritative. This tests whether selectors are robust to NOTE camouflage, not just NOTE labels.

```powershell
$outDir = "runs\note_camouflage_k4_s3q16"
goldevidencebench sweep --out $outDir --seeds 3 --episodes 1 --steps 240 --queries 16 `
  --state-modes kv_commentary --distractor-profiles note_camouflage `
  --adapter goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter --no-derived-queries `
  --no-twins --require-citations --results-json "$outDir\combined.json" `
  --max-book-tokens 400 --note-rate 0.30
python .\scripts\summarize_results.py --in "$outDir\combined.json" --out-json "$outDir\summary.json"
```

Selector training under spoofing (optional): export with `--authority-spoof-rate`/`--authority-spoof-seed` and train with `--spoof-penalty` to penalize spoofed candidates. This can be combined with `--hard-negatives` for wrong?UPDATE pressure.

V3-B order generalization (v8: spoofpen+hardneg, filter ON, spoof_rate=0.5, k=4, s3q16):

| order | value_acc | selection_rate | gold_support_selected_rate | wrong_update_rate | spoof_accept_rate | spoof_accept_rate_non_gold |
| --- | --- | --- | --- | --- | --- | --- |
| gold_first | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.3125 | 0.0000 |
| gold_middle | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.5000 | 0.0000 |
| gold_last | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.4375 | 0.0000 |
| shuffle | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.5000 | 0.0000 |

Runs: runs/authority_spoof_0.5_filter1_linear_spoofpen_hardneg_{gold_first,gold_middle,gold_last,shuffle}_k4_s3q16.

Interpretation: accuracy is order-invariant and spoof exposure does not cause wrong picks (spoof_accept_rate_non_gold = 0).

Note: the remaining bottleneck depends on the regime. With filter ON and the v8 selector, wrong-UPDATE selection is resolved in this setting; without the filter or without hard-negative training, wrong-UPDATE and NOTE authority errors reappear.

Filter-OFF check (v8, spoof_rate=0.5, k=4, s3q16): value_acc=0.6875, gold_support_selected_rate=0.6875, selected_note_rate=0.3125, spoof_accept_rate=0.625, spoof_accept_rate_non_gold=0.0.
Interpretation: without the authority filter, the selector still avoids wrong UPDATEs but accepts NOTE lines; the hard gate remains required.





**V3-C: Answer contract (extraction clamp)**

- Set `GOLDEVIDENCEBENCH_RETRIEVAL_DETERMINISTIC_ANSWER=1` to return the value parsed from the selected ledger line (no LLM).
- Set `GOLDEVIDENCEBENCH_RETRIEVAL_COPY_CLAMP=1` to require the answer value be an exact substring of the selected line; otherwise return null.
- Use this as an oracle upper bound: if accuracy_when_gold_present rises to selection_rate, the remaining gap was answerer/extraction.


V3-C results (kv_commentary, k=4 same_key, s3q16; authority filter ON + copy-clamp ON):

| order | value_acc | selection_rate | selected_note_rate | wrong_update_rate |
| --- | --- | --- | --- | --- |
| gold_first | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
| gold_middle | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
| gold_last | 0.9583 | 0.9583 | 0.0000 | 0.0417 |
| shuffle | 0.9792 | 0.9792 | 0.0000 | 0.0208 |

Runs: runs/kv_commentary_noteaware_copyclamp_filter_{gold_first,gold_middle,gold_last,shuffle}_k4_s3q16.

Interpretation: authority gating removes NOTE errors and copy-clamp removes extraction drift; remaining error is rare wrong-UPDATE selection.


Contrast (filter OFF + copy-clamp ON; same settings):

| order | value_acc | selection_rate | selected_note_rate | wrong_update_rate |
| --- | --- | --- | --- | --- |
| gold_first | 0.6875 | 1.0000 | 0.3125 | 0.0000 |
| gold_middle | 0.6875 | 1.0000 | 0.3125 | 0.0000 |
| gold_last | 0.6458 | 0.9583 | 0.3125 | 0.0417 |
| shuffle | 0.6875 | 1.0000 | 0.3125 | 0.0000 |

Runs: runs/kv_commentary_noteaware_copyclamp_{gold_first,gold_middle,gold_last,shuffle}_k4_s3q16.

Interpretation: copy-clamp fixes extraction, but NOTE authority errors remain without the filter (selected_note_rate ~31%).




**Architecture guardrail**

- Split authority gating (cheap classifier/rules/signature check) from content selection (reranker).
- Keep authority checks as hard gates so content plausibility cannot override it.

Proof run uses `linear` to match the reference tables; the default for general use is `prefer_update_latest`.

## Archived: current plan (update_burst wall, 2026-01)

## Current plan (update_burst wall, 2026-01)

Stress regime (linear + step_bucket=10 + k=16) with seeds=3 fails the wrong_update_rate gate (see
[configs/usecase_checks.json](../configs/usecase_checks.json)) even at update_burst_rate=0.02. That means this diagnostic
regime is beyond the configured gate threshold for any nonzero burst rate.
The earlier 1-seed wall (~0.18-0.19) was variance.

Seeds=3 pin runs used to locate the wall (full pipeline):

- `runs/wall_update_burst_full_linear_bucket10_pin_20260104_200253_s3` (0.175-0.19)
- `runs/wall_update_burst_full_linear_bucket10_pin_20260104_215915_s3_low` (0.10-0.17)
- `runs/wall_update_burst_full_linear_bucket10_pin_20260104_233152_s3_micro` (0.02-0.08)

Micro sweep (seeds=3; full pipeline, linear + step_bucket=10 + k=16):

| update_burst_rate | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- |
| 0.02 | 0.8750 | 0.1250 | 0.8750 |
| 0.04 | 0.7708 | 0.2292 | 0.7708 |
| 0.06 | 0.8125 | 0.1875 | 0.8125 |
| 0.08 | 0.7500 | 0.2500 | 0.7500 |

Step_bucket=5 pin run (seeds=3; full pipeline, linear + step_bucket=5 + k=16):

- `runs/wall_update_burst_full_linear_bucket5_pin_20260110_002140` (0.12, 0.14, 0.16, 0.18)
- `runs/wall_update_burst_full_linear_bucket5_adaptive_20260110_131216` (0.08, 0.12, 0.16, 0.168, 0.176, 0.184, 0.192, 0.20, 0.24)
- Stable gate path (frozen for checks): `runs/release_gates/update_burst_full_linear_k16_bucket5_rate0.12`

Legacy prefer_update_latest sweep (reference, not used in checks):

- `runs/update_burst_prefer_update_latest_gate_20260105_025033` (0.25, 0.35, 0.45)
- `runs/update_burst_prefer_update_latest_gate_20260105_133108_full_s3` (0.95)
- `runs/update_burst_prefer_update_latest_gate_20260105_142019_full_s3_099` (0.99)
 - Selector-only quick probe: `runs/update_burst_prefer_update_latest_gate_20260105_152002_quick5` (1.0; value_acc not meaningful)

| update_burst_rate | selection_rate | wrong_update_rate | value_acc |
| --- | --- | --- | --- |
| 0.25 | 1.0000 | 0.0000 | 1.0000 |
| 0.35 | 1.0000 | 0.0000 | 1.0000 |
| 0.45 | 1.0000 | 0.0000 | 1.0000 |
| 0.95 | 1.0000 | 0.0000 | 1.0000 |
| 0.99 | 1.0000 | 0.0000 | 1.0000 |

Selector-only auto-pin run (diagnostic only; value_acc not meaningful): `runs/wall_update_burst_20260104_190551`.

Plan going forward:

1) Keep the linear+bucket10 stress regime as diagnostic only (always beyond the configured gate threshold).
2) Use the linear+bucket5 gate at the configured update_burst_rate as the production check in
   [configs/usecase_checks.json](../configs/usecase_checks.json).
3) Re-run the adaptive sweep only when model/selector/k/bucket changes.
3) Wall not found up to 0.99; treat the production default as robust in update_burst at this scale.
4) Keep the UI same_label gate (`runs/ui_same_label_gate.json`) as a release check for UI-adapter readiness.

Canonical wall sweep commands (frozen):

```powershell
# Stress regime (full pipeline, linear + step_bucket=10 + k=16)
.\scripts\run_update_burst_full_linear_bucket10.ps1 `
  -ModelPath "<MODEL_PATH>" `
  -OutRoot "runs\wall_update_burst_full_linear_bucket10_20260104_180252" `
  -Rates 0.205,0.209,0.22,0.24

# Pin sweep (same regime, lower rates)
.\scripts\run_update_burst_full_linear_bucket10.ps1 `
  -ModelPath "<MODEL_PATH>" `
  -OutRoot "runs\wall_update_burst_full_linear_bucket10_pin_20260104_180252" `
  -Rates 0.18,0.19,0.195,0.20 `
  -FindWall:$true
```

# Aegislash Multi-Dataset Evaluation Results

This folder contains the test results, observations, and `report.json` outputs from evaluating Aegislash across 4 independent synthetic test datasets:

- [test_results_and_observations.md](test_results_and_observations.md) — Full comparison table, verbatim CLI outputs (`main.py`, `validate_output.py`, `check_dev.py`, `scripts/risk_report.py`), root-cause analysis, and red-team failure findings.
- [dataset_1_standard_report.json](dataset_1_standard_report.json) — `report.json` output on `Dataset_1_MultiHospital_Standard` (`0.1%` leaked, `0.93` F0.5, `CONTRACT OK`).
- [dataset_2_unseen_hindi_report.json](dataset_2_unseen_hindi_report.json) — `report.json` output on `Dataset_2_UnseenFormats_Hindi` (`0.0%` leaked, `0.86` F0.5, `CONTRACT OK`).
- [dataset_3_adversarial_chaos_report.json](dataset_3_adversarial_chaos_report.json) — `report.json` output on `Dataset_3_Adversarial_Chaos_Risk` (`0.6%` leaked, `0.94` F0.5, `CONTRACT OK`).
- [dataset_4_adversarial_breaker_report.json](dataset_4_adversarial_breaker_report.json) — `report.json` output on `Dataset_4_Adversarial_Breaker` (`25.1%` leaked, `9/16` canaries, `0.40` F0.5, `CONTRACT OK`).

## IO & Cross-Module Breaker Suite (Member-1 / `io`)

- [io_adversarial_results.md](io_adversarial_results.md) — Exact raw CLI outputs (`main.py`, `validate_output.py`, `check_dev.py`) for `adversarial_input` and 3 targeted breaker datasets (`breaker_ds1_io_formats`, `breaker_ds2_detect_bypass`, `breaker_ds3_link_privacy`), plus code-verified root-cause analysis.
- [io_adversarial_report.json](io_adversarial_report.json) — `report.json` output from running `dev/adversarial_input` (`16` files, `10040` records, `CONTRACT OK`).
- [breaker_ds1_io_formats_report.json](breaker_ds1_io_formats_report.json) — `report.json` output for `breaker_ds1_io_formats` (`11` files, `1` quarantined, `1` raw copy leak).
- [breaker_ds2_detect_bypass_report.json](breaker_ds2_detect_bypass_report.json) — `report.json` output for `breaker_ds2_detect_bypass` (`6` files, `13` records).
- [breaker_ds3_link_privacy_report.json](breaker_ds3_link_privacy_report.json) — `report.json` output for `breaker_ds3_link_privacy` (`4` files, `14` records).
- [breakers/](breakers/) — Reproducible input files, `truth/truth.json`, and manifests for all 4 adversarial/breaker datasets.

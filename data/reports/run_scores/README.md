# run_scores — raw per-seed scores from the stage-3 ablations

61 KB standing in for 14.6 GB of weights.

Every stage-3 variant in `docs/RESULTS.md` section 5b was trained, measured, and
then deleted once it had lost. The weights were the disposable part: ~568 MB of
`model.safetensors` per seed, regenerable in about five minutes on a GPU because
the stage-2 and stage-2b encoders they were built from are kept.

What was *not* disposable is what each run scored. These files are that:

| file | what |
|---|---|
| `scores_test_raw.npy` | raw model output on the 123-row frozen test set |
| `scores_val_raw.npy` | raw output on the 57-row validation split |
| `y_val.npy` | validation labels |
| `calibration.json` | the Platt map fitted on that run's validation scores |
| `run_meta.json` | source encoder, threshold, band margin, measured metrics |

With these, the comparisons in RESULTS.md can be re-derived on a CPU in seconds
and without the model:

* the paired bootstrap in section 5c — verified to reproduce
  `delta +0.0245, 95% CI [-0.0699, +0.1215], P(better) = 0.70` exactly from
  these files alone;
* `python -m ml.calibration --refit-all`, if the calibrator ever changes.

Scores are **raw**, pre-calibration. Apply the matching `calibration.json`
before comparing anything to a published figure — the map is monotonic, so it
cannot move PR-AUC, ROC-AUC or precision@k, but it does move Brier and anything
threshold-dependent.

The one checkpoint whose weights are kept is the promoted model,
`model_artifacts/deberta_sif/stilt_reset_hlr20/seed2`, which is also published as
a GitHub Release and fetched by `ml/fetch_model.py`.

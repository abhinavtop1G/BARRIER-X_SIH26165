# v1_pre_fix — results from before the calibration and export fixes

Kept so the change is measurable rather than asserted. These are the original
3-seed stage-3 numbers, produced with:

* no discriminative learning rate, so the classifier head was still at
  initialisation (weight norm 0.753 against an init norm of 0.784) and every
  test probability fell in [0.494, 0.581];
* no calibration, so those probabilities were not probabilities;
* a threshold matched to a checkpoint by reverse filename sort.

The ranking metrics here (PR-AUC, ROC-AUC, precision@k) are directly comparable
to the current run: calibration is monotonic and does not move them. The
threshold-dependent ones (precision, recall, F1, Brier) are not comparable,
because the operating point they were measured at was not reproducible.

See docs/RESULTS.md for the side-by-side.

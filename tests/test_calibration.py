"""Calibration properties."""

from __future__ import annotations

import numpy as np
import pytest

from ml.artifacts import band_margin_for
from ml.calibration import Calibrator, expected_calibration_error, log_loss


def _scores(n=400, seed=0, spread=0.03):
    """A good ranking compressed into a narrow band around 0.5 -- the exact"""
    rng = np.random.default_rng(seed)
    y = rng.binomial(1, 0.4, n)
    s = 0.5 + spread * (y * 2 - 1) * rng.random(n) + 0.01 * rng.standard_normal(n)
    return y.astype(float), s


def test_calibration_is_monotonic():
    y, s = _scores()
    cal = Calibrator.fit(y[:57], s[:57])
    order = np.argsort(s)
    assert np.all(np.diff(cal(s)[order]) >= -1e-12)


def test_ranking_metrics_are_unchanged():
    from sklearn.metrics import average_precision_score, roc_auc_score

    y, s = _scores()
    cal = Calibrator.fit(y[:57], s[:57])
    p = cal(s)
    assert average_precision_score(y, s) == pytest.approx(average_precision_score(y, p), abs=1e-9)
    assert roc_auc_score(y, s) == pytest.approx(roc_auc_score(y, p), abs=1e-9)
    assert np.array_equal(np.argsort(s), np.argsort(p))


def test_calibration_widens_a_compressed_distribution():
    y, s = _scores()
    p = Calibrator.fit(y[:57], s[:57])(s)
    assert (s.max() - s.min()) < 0.15, "fixture should start compressed"
    assert (p.max() - p.min()) > 0.5, "calibration must spread the scale out"


def test_calibration_improves_log_loss_on_its_own_fit_data():
    y, s = _scores()
    yv, sv = y[:57], s[:57]
    assert log_loss(yv, Calibrator.fit(yv, sv)(sv)) <= log_loss(yv, sv) + 1e-9


def test_platt_converges_on_near_separable_data():
    """The regression test. Overconfident, near-separable, with a few confident"""
    rng = np.random.default_rng(7)
    n = 57
    y = rng.binomial(1, 0.4, n).astype(float)
    s = np.where(y == 1, rng.uniform(0.55, 0.997, n), rng.uniform(0.006, 0.45, n))
    s[rng.choice(n, 6, replace=False)] = 1 - s[rng.choice(n, 6, replace=False)]

    cal = Calibrator.fit(y, s, method="platt")
    assert np.isfinite(cal.params["a"]) and np.isfinite(cal.params["b"])
    assert log_loss(y, cal(s)) < log_loss(y, s), "must beat the uncalibrated scores"
    assert expected_calibration_error(y, cal(s)) < expected_calibration_error(y, s)


def test_auto_never_chooses_something_worse_than_identity():
    y, s = _scores()
    cal = Calibrator.fit(y[:57], s[:57])
    considered = cal.fitted_on["considered"]
    assert considered[cal.method] == min(considered.values())


def test_isotonic_is_withheld_on_small_validation_sets():
    """57 rows cannot support a free-form step function."""
    y, s = _scores()
    assert "isotonic" not in Calibrator.fit(y[:57], s[:57]).fitted_on["considered"]


def test_save_load_round_trip(tmp_path):
    y, s = _scores()
    cal = Calibrator.fit(y[:57], s[:57])
    path = tmp_path / "calibration.json"
    cal.save(path)
    assert np.allclose(cal(s), Calibrator.load(path)(s))


def test_identity_calibrator_is_a_no_op():
    _, s = _scores()
    assert np.array_equal(Calibrator.identity()(s), s)


def test_output_stays_in_the_unit_interval():
    y, s = _scores()
    p = Calibrator.fit(y[:57], s[:57])(np.array([0.0, 1e-9, 0.5, 1 - 1e-9, 1.0]))
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_band_margin_keeps_high_and_low_reachable():
    """The API once used a fixed +/-0.15 against a 0.06-wide score range, which"""
    val = np.linspace(0.20, 0.60, 50)
    thr = 0.30
    m = band_margin_for(thr, val)
    assert thr + m <= val.max(), "HIGH must be reachable"
    assert thr - m >= val.min(), "LOW must be reachable"


def test_band_margin_shrinks_for_a_threshold_near_the_edge():
    val = np.linspace(0.20, 0.60, 50)
    assert band_margin_for(0.22, val) < band_margin_for(0.40, val)


def test_band_margin_is_capped_and_floored():
    wide = np.linspace(0.0, 1.0, 50)
    assert band_margin_for(0.5, wide) <= 0.15
    assert band_margin_for(0.5, np.array([0.499, 0.501])) >= 0.02
    assert band_margin_for(0.5, np.array([])) == 0.15

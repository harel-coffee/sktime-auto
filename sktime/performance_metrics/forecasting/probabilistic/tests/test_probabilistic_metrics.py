"""Tests for probabilistic performance metrics."""
import warnings

import numpy as np
import pandas as pd
import pytest

from sktime.forecasting.model_selection import temporal_train_test_split
from sktime.forecasting.naive import NaiveForecaster, NaiveVariance
from sktime.performance_metrics.forecasting.probabilistic import (
    ConstraintViolation,
    EmpiricalCoverage,
    PinballLoss,
)
from sktime.utils._testing.series import _make_series

warnings.filterwarnings("ignore", category=FutureWarning)

quantile_metrics = [
    PinballLoss,
]

interval_metrics = [
    EmpiricalCoverage,
    ConstraintViolation,
]

all_metrics = interval_metrics + quantile_metrics

alpha_s = [0.5]
alpha_m = [0.05, 0.5, 0.95]
coverage_s = 0.9
coverage_m = [0.7, 0.8, 0.9, 0.99]


@pytest.fixture
def sample_data(request):
    n_columns, coverage_or_alpha, pred_type = request.param

    y = _make_series(n_columns=n_columns)
    y_train, y_test = temporal_train_test_split(y)
    fh = np.arange(len(y_test)) + 1

    # fit model
    f = NaiveVariance(NaiveForecaster())
    f.fit(y_train)

    # predict model

    if pred_type == "interval":
        interval_pred = f.predict_interval(fh=fh, coverage=coverage_or_alpha)
        return y_test, interval_pred

    elif pred_type == "quantile":
        quantile_pred = f.predict_quantiles(fh=fh, alpha=coverage_or_alpha)
        return y_test, quantile_pred

    return


# Test the parametrized fixture
@pytest.mark.parametrize(
    "sample_data",
    [
        (1, alpha_s, "quantile"),
        (3, alpha_s, "quantile"),
        (1, alpha_m, "quantile"),
        (3, alpha_m, "quantile"),
        (1, coverage_s, "interval"),
        (3, coverage_s, "interval"),
        (1, coverage_m, "interval"),
        (3, coverage_m, "interval"),
    ],
    indirect=True,
)
def test_sample_data(sample_data):
    y_true, y_pred = sample_data
    assert isinstance(y_true, (pd.Series, pd.DataFrame))
    assert isinstance(y_pred, pd.DataFrame)


def helper_check_output(metric, score_average, multioutput, sample_data):
    y_true, y_pred = sample_data
    """Test output is correct class and shape for given data."""
    loss = metric.create_test_instance()
    loss.set_params(score_average=score_average, multioutput=multioutput)

    eval_loss = loss(y_true, y_pred)
    index_loss = loss.evaluate_by_index(y_true, y_pred)

    no_vars = len(y_pred.columns.get_level_values(0).unique())
    no_scores = len(y_pred.columns.get_level_values(1).unique())

    if (
        0.5 in y_pred.columns.get_level_values(1)
        and loss.get_tag("scitype:y_pred") == "pred_interval"
        and y_pred.columns.nlevels == 2
    ):
        no_scores = no_scores - 1
        no_scores = no_scores / 2  # one interval loss per two quantiles given
        if no_scores == 0:  # if only 0.5 quant, no output to interval loss
            no_vars = 0

    if score_average and multioutput == "uniform_average":
        assert isinstance(eval_loss, float)
        assert isinstance(index_loss, pd.Series)

        assert len(index_loss) == y_pred.shape[0]

    if not score_average and multioutput == "uniform_average":
        assert isinstance(eval_loss, pd.Series)
        assert isinstance(index_loss, pd.DataFrame)

        # get two quantiles from each interval so if not score averaging
        # get twice number of unique coverages
        if (
            loss.get_tag("scitype:y_pred") == "pred_quantiles"
            and y_pred.columns.nlevels == 3
        ):
            assert len(eval_loss) == 2 * no_scores
        else:
            assert len(eval_loss) == no_scores

    if not score_average and multioutput == "raw_values":
        assert isinstance(eval_loss, pd.Series)
        assert isinstance(index_loss, pd.DataFrame)

        true_len = no_vars * no_scores

        if (
            loss.get_tag("scitype:y_pred") == "pred_quantiles"
            and y_pred.columns.nlevels == 3
        ):
            assert len(eval_loss) == 2 * true_len
        else:
            assert len(eval_loss) == true_len

    if score_average and multioutput == "raw_values":
        assert isinstance(eval_loss, pd.Series)
        assert isinstance(index_loss, pd.DataFrame)

        assert len(eval_loss) == no_vars


@pytest.mark.parametrize(
    "sample_data",
    [
        (1, alpha_s, "quantile"),
        (3, alpha_s, "quantile"),
        (1, alpha_m, "quantile"),
        (3, alpha_m, "quantile"),
    ],
    indirect=True,
)
@pytest.mark.parametrize("metric", all_metrics)
@pytest.mark.parametrize("multioutput", ["uniform_average", "raw_values"])
@pytest.mark.parametrize("score_average", [True, False])
def test_output_quantiles(metric, score_average, multioutput, sample_data):
    helper_check_output(metric, score_average, multioutput, sample_data)


@pytest.mark.parametrize(
    "sample_data",
    [
        (1, coverage_s, "interval"),
        (3, coverage_s, "interval"),
        (1, coverage_m, "interval"),
        (3, coverage_m, "interval"),
    ],
    indirect=True,
)
@pytest.mark.parametrize("metric", all_metrics)
@pytest.mark.parametrize("multioutput", ["uniform_average", "raw_values"])
@pytest.mark.parametrize("score_average", [True, False])
def test_output_intervals(metric, score_average, multioutput, sample_data):
    helper_check_output(metric, score_average, multioutput, sample_data)


@pytest.mark.parametrize("metric", quantile_metrics)
@pytest.mark.parametrize(
    "sample_data",
    [
        (1, alpha_s, "quantile"),
        (3, alpha_s, "quantile"),
        (1, alpha_m, "quantile"),
        (3, alpha_m, "quantile"),
    ],
    indirect=True,
)
def test_evaluate_alpha_positive(metric, sample_data):
    """Tests output when required quantile is present."""
    # 0.5 in test quantile data don't raise error.

    y_true, y_pred = sample_data

    Loss = metric.create_test_instance().set_params(alpha=0.5, score_average=False)
    res = Loss(y_true=y_true, y_pred=y_pred)
    assert len(res) == 1

    if all(x in y_pred.columns.get_level_values(1) for x in [0.5, 0.95]):
        Loss = metric.create_test_instance().set_params(
            alpha=[0.5, 0.95], score_average=False
        )
        res = Loss(y_true=y_true, y_pred=y_pred)
        assert len(res) == 2


# This test tests quantile data
@pytest.mark.parametrize(
    "sample_data",
    [
        (1, alpha_s, "quantile"),
        (3, alpha_s, "quantile"),
        (1, alpha_m, "quantile"),
        (3, alpha_m, "quantile"),
    ],
    indirect=True,
)
@pytest.mark.parametrize("metric", quantile_metrics)
def test_evaluate_alpha_negative(metric, sample_data):
    """Tests whether correct error raised when required quantile not present."""
    y_true, y_pred = sample_data
    with pytest.raises(ValueError):
        # 0.3 not in test quantile data so raise error.
        Loss = metric.create_test_instance().set_params(alpha=0.3)
        res = Loss(y_true=y_true, y_pred=y_pred)  # noqa

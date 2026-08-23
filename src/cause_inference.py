# src/02_cause_inference.py
import pandas as pd
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from collections import Counter


# A top class below this probability is insufficient for an automatic
# diagnosis, even when no signature-equivalence rule has fired.
MIN_RESOLVED_CONFIDENCE = 0.60

def prepare_feature_matrix(features_df,exclude_scenarios=('baseline',)):
    """
    Pivots each residual-window statistic per sensor into one case-level row.

    A mean-only vector cannot distinguish a persistent sensor bias from a
    stuck sensor whose error varies over the diurnal cycle. Keep mean, max,
    and standard deviation as independent temporal features.
    """
    pivoted = features_df.pivot_table(
        index=['scenario', 'case_id'], 
        columns='sensor', 
        values=['mean_res', 'max_res', 'std_res']
    ).fillna(0.0)
    pivoted.columns = [f"{sensor}__{statistic}" for statistic, sensor in pivoted.columns]
    pivoted = pivoted.reset_index()

    # These sensor-invariant summaries let the classifier learn a fault's
    # physical shape even when its affected sensor is held out of training.
    # For example: bias has a large, near-zero-variance residual at one sensor;
    # a stuck sensor has a time-varying residual at one sensor.
    for statistic in ('mean_res', 'max_res', 'std_res'):
        statistic_columns = [
            column for column in pivoted.columns if column.endswith(f'__{statistic}')
        ]
        pivoted[f'summary__max_{statistic}'] = pivoted[statistic_columns].max(axis=1)
        pivoted[f'summary__mean_{statistic}'] = pivoted[statistic_columns].mean(axis=1)
    mean_columns = [
        column for column in pivoted.columns if column.endswith('__mean_res')
    ]
    pivoted['summary__affected_sensor_count'] = (
        pivoted[mean_columns].gt(0.10).sum(axis=1)
    )

    pivoted = pivoted[~pivoted['scenario'].isin(exclude_scenarios)]
    return pivoted


def _event_feature_values(sensor_order, sample_feature_dict):
    """Return an event vector in model-column order.

    Preferred input uses keys such as ``n105__mean_res`` and
    ``n105__std_res``. Plain ``n105`` keys remain supported for older callers
    as a mean-only value; max is then assumed equal to the mean and standard
    deviation is zero.
    """
    values = []
    for feature_name in sensor_order:
        if feature_name in sample_feature_dict:
            values.append(sample_feature_dict[feature_name])
            continue

        if feature_name.startswith('summary__'):
            summary_name = feature_name.removeprefix('summary__')
            if summary_name == 'affected_sensor_count':
                mean_values = [
                    value for name, value in sample_feature_dict.items()
                    if name.endswith('__mean_res')
                ]
                values.append(sum(value > 0.10 for value in mean_values))
                continue

            aggregation, statistic = summary_name.split('_', 1)
            statistic_values = [
                value for name, value in sample_feature_dict.items()
                if name.endswith(f'__{statistic}')
            ]
            if statistic_values:
                values.append(
                    max(statistic_values) if aggregation == 'max'
                    else float(np.mean(statistic_values))
                )
                continue
            values.append(0.0)
            continue

        sensor, statistic = feature_name.rsplit('__', 1)
        legacy_mean = sample_feature_dict.get(sensor, 0.0)
        values.append(legacy_mean if statistic in ('mean_res', 'max_res') else 0.0)
    return values

def train_cause_classifier(train_matrix_df, calibrate=True):
    """
    Trains XGBoost to predict the cause family (scenario), then calibrates
    the output probabilities so they reflect true confidence (needed for
    Brier score / ECE reporting).
    """
    le = LabelEncoder()
    y = le.fit_transform(train_matrix_df['scenario'])
    X = train_matrix_df.drop(columns=['scenario', 'case_id'])

    base_model = XGBClassifier(
        n_estimators=50,
        max_depth=3,
        eval_metric='mlogloss',
        random_state=42
    )

    # Calibration (esp. isotonic) needs enough samples per class to be
    # meaningful. If any class is too small, fall back to the raw model
    # rather than silently producing garbage calibration.
    min_class_count = min(Counter(y).values())
    safe_cv = min(3, min_class_count)

    if calibrate and safe_cv >= 2:
        model = CalibratedClassifierCV(base_model, method='sigmoid', cv=safe_cv)
        model.fit(X, y)
    else:
        print(f"[WARN] Skipping calibration — smallest class has only "
              f"{min_class_count} samples (need >=2 per fold). Using raw model.")
        model = base_model
        model.fit(X, y)

    return model, le, X.columns.tolist()


def get_calibrated_posterior(model, le, sensor_order, sample_res_dict):
    """
    Given a single event's residual-window feature dictionary, predicts the
    calibrated probability distribution across cause families.
    """
    sample_df = pd.DataFrame(
        [_event_feature_values(sensor_order, sample_res_dict)], columns=sensor_order
    )
    probs = model.predict_proba(sample_df)[0]
    return dict(zip(le.classes_, probs))

def find_nearest_case(matrix_df, sensor_order, sample_res_dict):
    """
    Finds the case_id whose residual signature is closest (Euclidean)
    to the live event's observed residuals. This is what lets us check
    identifiability at the right granularity.
    """
    sample_vec = np.array(_event_feature_values(sensor_order, sample_res_dict))
    feature_cols = matrix_df[sensor_order].values

    dists = np.linalg.norm(feature_cols - sample_vec, axis=1)
    nearest_idx = int(np.argmin(dists))

    return {
        'case_id': matrix_df.iloc[nearest_idx]['case_id'],
        'scenario': matrix_df.iloc[nearest_idx]['scenario'],
        'distance': float(dists[nearest_idx])
    }

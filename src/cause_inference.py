# src/02_cause_inference.py
import pandas as pd
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from collections import Counter

def prepare_feature_matrix(features_df,exclude_scenarios=('baseline',)):
    """
    Pivots features so each row is a case_id and columns are residuals per sensor.
    """
    pivoted = features_df.pivot_table(
        index=['scenario', 'case_id'], 
        columns='sensor', 
        values='mean_res'
    ).fillna(0.0).reset_index()

    pivoted = pivoted[~pivoted['scenario'].isin(exclude_scenarios)]
    return pivoted

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
    Given a single event's sensor residuals {sensor_name: mean_residual},
    predicts the calibrated probability distribution across cause families.
    """
    sample_df = pd.DataFrame([[sample_res_dict.get(s, 0.0) for s in sensor_order]], columns=sensor_order)
    probs = model.predict_proba(sample_df)[0]
    return dict(zip(le.classes_, probs))

def find_nearest_case(matrix_df, sensor_order, sample_res_dict):
    """
    Finds the case_id whose residual signature is closest (Euclidean)
    to the live event's observed residuals. This is what lets us check
    identifiability at the right granularity.
    """
    sample_vec = np.array([sample_res_dict.get(s, 0.0) for s in sensor_order])
    feature_cols = matrix_df[sensor_order].values

    dists = np.linalg.norm(feature_cols - sample_vec, axis=1)
    nearest_idx = int(np.argmin(dists))

    return {
        'case_id': matrix_df.iloc[nearest_idx]['case_id'],
        'scenario': matrix_df.iloc[nearest_idx]['scenario'],
        'distance': float(dists[nearest_idx])
    }
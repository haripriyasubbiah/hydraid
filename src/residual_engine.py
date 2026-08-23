# src/01_residual_engine.py
import pandas as pd
import numpy as np

def compute_residuals(df_signatures, df_observed):
    """
    df_signatures: DataFrame with [scenario, case_id, sensor, time, pressure]
    df_observed: DataFrame with [sensor, time, pressure] (live/test event readings)
    """
    # Merge on sensor and time
    merged = pd.merge(
        df_signatures, 
        df_observed, 
        on=['sensor', 'time'], 
        suffixes=('_sim', '_obs')
    )
    # Calculate absolute residual
    merged['residual'] = np.abs(merged['pressure_sim'] - merged['pressure_obs'])
    return merged

def extract_window_features(df_residuals):
    """
    Aggregates residuals per hypothesis (case_id) into feature vectors.
    """
    features = df_residuals.groupby(['scenario', 'case_id', 'sensor'])['residual'].agg(
        mean_res='mean',
        max_res='max',
        std_res='std'
    ).reset_index()
    
    # Fill any single-point std NaNs with 0
    features['std_res'] = features['std_res'].fillna(0.0)
    return features
import pandas as pd
import numpy as np

df = pd.read_csv('signatures.csv')

# Get baseline for residual calc
baseline = df[df['scenario'] == 'baseline'][['sensor', 'time', 'pressure']]

# Pick one real bias case_id
bias_cases = df[df['scenario'] == 'bias']['case_id'].unique()
print("Available bias case_ids:", bias_cases)

chosen_case = bias_cases[0]  # just take the first one for now
print(f"\nUsing case: {chosen_case}")

case_data = df[(df['scenario'] == 'bias') & (df['case_id'] == chosen_case)]

merged = pd.merge(case_data, baseline, on=['sensor', 'time'], suffixes=('_sim', '_base'))
merged['residual'] = np.abs(merged['pressure_sim'] - merged['pressure_base'])

# This matches what extract_window_features does — mean residual per sensor
mean_res_per_sensor = merged.groupby('sensor')['residual'].mean().to_dict()
print("\nReal bias test event (paste this into your test file):")
print(mean_res_per_sensor)
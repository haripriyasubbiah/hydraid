

import pandas as pd
df = pd.read_csv('signatures.csv')
baseline = df[df['scenario'] == 'baseline'][['sensor', 'time', 'pressure']]

leak_cases = df[df['scenario'] == 'leak']['case_id'].unique()
chosen = leak_cases[0]
case_data = df[(df['scenario']=='leak') & (df['case_id']==chosen)]

merged = pd.merge(case_data, baseline, on=['sensor','time'], suffixes=('_sim','_base'))
merged['residual'] = (merged['pressure_sim'] - merged['pressure_base']).abs()

leak_test_event = merged.groupby('sensor')['residual'].mean().to_dict()
print(f"Using leak case: {chosen}")
print(leak_test_event)
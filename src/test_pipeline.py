# src/pipeline.py
import pandas as pd
try:
    from src.residual_engine import compute_residuals, extract_window_features
    from src.cause_inference import MIN_RESOLVED_CONFIDENCE, prepare_feature_matrix, train_cause_classifier, get_calibrated_posterior,find_nearest_case
    from src.identifiability import find_ambiguous_hypotheses,check_case_ambiguity
    from src.active_check import rank_next_sensor_checks
except ModuleNotFoundError:
    from residual_engine import compute_residuals, extract_window_features
    from cause_inference import MIN_RESOLVED_CONFIDENCE, prepare_feature_matrix, train_cause_classifier, get_calibrated_posterior,find_nearest_case
    from identifiability import find_ambiguous_hypotheses,check_case_ambiguity
    from active_check import rank_next_sensor_checks


# (add find_nearest_case and check_case_ambiguity to your existing imports)

def run_diagnostic_pipeline(signatures_path, sample_event_residuals, signatures_df=None):
    """Diagnose one event from residual-window features.

    Preferred event keys look like ``n105__mean_res``, ``n105__max_res``, and
    ``n105__std_res``. Mean-only sensor dictionaries remain supported for
    backwards compatibility.
    """
    df_sig = signatures_df.copy() if signatures_df is not None else pd.read_csv(signatures_path)

    ambiguities = find_ambiguous_hypotheses(df_sig, noise_tolerance=0.10)

    baseline = df_sig[df_sig['scenario'] == 'baseline'][['sensor', 'time', 'pressure']]
    residuals = compute_residuals(df_sig, baseline)
    feat_df = extract_window_features(residuals)
    matrix_df = prepare_feature_matrix(feat_df)

    model, le, sensor_order = train_cause_classifier(matrix_df)
    print("\n[Calibration check] Model type:", type(model).__name__)
    posterior = get_calibrated_posterior(model, le, sensor_order, sample_event_residuals)

    # NEW: find which specific hypothesis this event resembles
    nearest = find_nearest_case(matrix_df, sensor_order, sample_event_residuals)

    # NEW: check identifiability at the RIGHT granularity — is the nearest
    # matching case entangled with a case from a different cause family?
    equivalence = check_case_ambiguity(nearest['case_id'], ambiguities)

    top_cause = max(posterior, key=posterior.get)
    top_confidence = posterior[top_cause]
    if equivalence is not None and len(equivalence['scenarios_involved']) > 1:
        decision = {
            'status': 'ABSTAIN',
            'reason': f"Nearest hypothesis '{nearest['case_id']}' is observationally "
                      f"equivalent to case(s) from a different cause family.",
            'equivalence_class': equivalence
        }
    elif top_confidence < MIN_RESOLVED_CONFIDENCE:
        decision = {
            'status': 'ABSTAIN',
            'reason': (
                f"Top cause '{top_cause}' has calibrated confidence "
                f"{top_confidence:.1%}, below the {MIN_RESOLVED_CONFIDENCE:.0%} "
                "automatic-resolution threshold."
            )
        }
    else:
        decision = {
            'status': 'RESOLVED',
            'top_cause': top_cause,
            'confidence': top_confidence,
        }

        # Candidate set to discriminate between: if abstaining, it's the
    # equivalence class; if resolved, there's nothing ambiguous to separate
    candidate_case_ids = (
        equivalence['equivalent_cases'] if equivalence is not None else [nearest['case_id']]
    )

    candidate_sensors = sorted({
        feature_name.rsplit('__', 1)[0] for feature_name in sensor_order
    })
    ranked_actions = rank_next_sensor_checks(
        posterior, candidate_sensors,
        df_signatures=df_sig,
        candidate_case_ids=candidate_case_ids
    )
    return posterior, ambiguities, ranked_actions, decision

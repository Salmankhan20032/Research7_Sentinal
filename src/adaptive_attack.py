"""
Adaptive Adversary Attack Simulator for SENTINEL.
Empirically evaluates the minimum number of commands N_evade required for an adaptive
adversary to achieve target setpoint drift \Delta V without exceeding clear threshold \tau_{clear} = 0.45.
"""

import json
import math
import random
from pathlib import Path
import joblib
import numpy as np

SEED = 20260724
np.random.seed(SEED)
random.seed(SEED)

FEATURES = [
    "op_read", "op_write", "op_setpoint", "value_norm", "delta_norm",
    "interarrival_log", "hour_sin", "hour_cos", "role_permission", "origin_trust",
    "nonce_fresh", "repeat_similarity", "cross_sensor_residual", "within_safe_envelope",
    "rate_z", "session_progress", "device_pump", "device_valve", "device_heater"
]
SEQ_LEN = 48

def extract_features(window_matrix):
    res = []
    w_len = len(window_matrix)
    k_arr = np.arange(1, w_len + 1)
    k_mean = (w_len + 1) / 2.0
    denom = np.sum((k_arr - k_mean) ** 2)

    for j in range(len(FEATURES)):
        col = window_matrix[:, j]
        mean_val = np.mean(col)
        std_val = np.std(col)
        min_val = np.min(col)
        max_val = np.max(col)
        end_start = col[-1] - col[0]
        slope_val = np.sum((k_arr - k_mean) * (col - mean_val)) / denom if denom != 0 else 0.0
        q25 = np.percentile(col, 25)
        q75 = np.percentile(col, 75)
        res.extend([mean_val, std_val, min_val, max_val, end_start, slope_val, q25, q75])
    return np.array(res, dtype=np.float32)

def simulate_adaptive_attack(model, scaler, class_map, target_delta_v, max_steps=300):
    rng = np.random.default_rng(42)
    history = []
    base_val = 0.50
    for t in range(SEQ_LEN):
        row = np.zeros(len(FEATURES), dtype=np.float32)
        row[0] = 1.0  # op_read
        row[3] = base_val + rng.normal(0, 0.01)
        row[5] = math.log(1.0)
        row[6] = math.sin(2 * math.pi * (12 + t * 0.01) / 24)
        row[7] = math.cos(2 * math.pi * (12 + t * 0.01) / 24)
        row[8] = 1.0   # role perm
        row[9] = 0.95  # origin trust
        row[10] = 1.0  # nonce fresh
        row[11] = 0.1  # repeat sim
        row[12] = 0.01 # residual
        row[13] = 1.0  # safe env
        row[14] = 0.0
        row[15] = t / (SEQ_LEN - 1)
        row[17] = 1.0  # device valve
        history.append(row)

    cumulative_shift = 0.0
    steps = 0
    evaded_successfully = False
    detected_at_step = None
    scores_history = []

    for step in range(max_steps):
        if cumulative_shift >= target_delta_v:
            evaded_successfully = True
            break
        
        steps += 1
        best_delta = 0.0
        best_score = 1.0
        
        for candidate_delta in np.linspace(0.0001, 0.015, 30):
            cand_row = np.copy(history[-1])
            cand_row[0] = 0.0
            cand_row[2] = 1.0
            cand_row[3] += candidate_delta
            cand_row[4] = candidate_delta
            cand_row[12] += candidate_delta * 0.20
            
            cand_window = np.array(history[-(SEQ_LEN-1):] + [cand_row])
            feats = extract_features(cand_window)
            feats_scaled = scaler.transform(feats.reshape(1, -1))
            probs = model.predict_proba(feats_scaled)[0]
            norm_idx = class_map.get("normal", 0)
            score = 1.0 - probs[norm_idx]

            if score < 0.45 and candidate_delta > best_delta:
                best_delta = candidate_delta
                best_score = score
        
        if best_delta == 0.0:
            # If no positive drift is possible sub-threshold, try a read step to decay slope
            read_row = np.copy(history[-1])
            read_row[0] = 1.0
            read_row[2] = 0.0
            read_row[4] = 0.0
            cand_window = np.array(history[-(SEQ_LEN-1):] + [read_row])
            feats = extract_features(cand_window)
            feats_scaled = scaler.transform(feats.reshape(1, -1))
            probs = model.predict_proba(feats_scaled)[0]
            norm_idx = class_map.get("normal", 0)
            score = 1.0 - probs[norm_idx]
            
            if score < 0.45:
                best_delta = 0.0
                best_score = score
            else:
                detected_at_step = steps
                break
            
        new_row = np.copy(history[-1])
        if best_delta > 0:
            new_row[0] = 0.0
            new_row[2] = 1.0
            new_row[3] += best_delta
            new_row[4] = best_delta
            new_row[12] += best_delta * 0.20
            cumulative_shift += best_delta
        else:
            new_row[0] = 1.0
            new_row[2] = 0.0
            new_row[4] = 0.0
            
        history.append(new_row)
        scores_history.append(best_score)

    return {
        "target_delta_v": target_delta_v,
        "achieved_delta_v": round(float(cumulative_shift), 4),
        "steps_taken": steps,
        "evaded_successfully": evaded_successfully,
        "detected_at_step": detected_at_step,
        "mean_score": round(float(np.mean(scores_history)) if scores_history else 1.0, 4)
    }

def main():
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    model_data = joblib.load("results/sentinel_scorer.joblib")
    model = model_data["model"]
    scaler = model_data["scaler"]
    classes = list(model_data["classes"])
    class_map = {c: i for i, c in enumerate(classes)}

    targets = [0.20, 0.40, 0.60, 0.80, 1.00]
    attack_results = []

    for t_val in targets:
        res = simulate_adaptive_attack(model, scaler, class_map, t_val)
        attack_results.append(res)
        print(f"Target Delta V={t_val}: Achieved={res['achieved_delta_v']}, Steps={res['steps_taken']}, Evaded={res['evaded_successfully']}")

    out_file = results_dir / "adaptive_attack.json"
    with open(out_file, "w") as f:
        json.dump(attack_results, f, indent=2)
    print(f"Saved adaptive attack results to {out_file}")

if __name__ == "__main__":
    main()

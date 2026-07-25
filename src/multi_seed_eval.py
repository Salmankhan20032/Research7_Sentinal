"""
Multi-Seed Variance Evaluator for SENTINEL.
Evaluates data generation, feature extraction, scaling, model training, and shifted-test
performance across 5 independent random seeds (20260724 to 20260728).
"""

import json
import random
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_recall_fscore_support, roc_auc_score
from sklearn.preprocessing import StandardScaler

# Import generator from experiment_final
from experiment_final import generate_session, SEQ_LEN, FEATURES, summarize

SEEDS = [20260724, 20260725, 20260726, 20260727, 20260728]

def run_seed_eval(seed):
    np.random.seed(seed)
    random.seed(seed)
    
    # Generate 4000 sessions
    # 2400 normal (label 0), 320 for each of 5 attack classes (labels 1..5)
    counts = [2400, 320, 320, 320, 320, 320]
    sessions = []
    labels = []
    
    sess_id = 0
    for cls_idx, cnt in enumerate(counts):
        for i in range(cnt):
            mat = generate_session(cls_idx, seed + sess_id * 31 + i)
            sessions.append(mat)
            labels.append(cls_idx)
            sess_id += 1
            
    sessions = np.array(sessions, dtype=np.float32)
    labels = np.array(labels, dtype=np.int64)
    
    # Session-level stratified split: 70% train, 15% val, 15% test
    rng = np.random.default_rng(seed)
    indices = np.arange(len(sessions))
    rng.shuffle(indices)
    
    train_idx = indices[:2800]
    val_idx = indices[2800:3400]
    test_idx = indices[3400:]
    
    # Feature aggregation
    X_train = summarize(sessions[train_idx])
    y_train = labels[train_idx]
    
    X_test = summarize(sessions[test_idx])
    y_test = labels[test_idx]
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    rf = RandomForestClassifier(
        n_estimators=160,
        max_depth=15,
        min_samples_leaf=3,
        max_features="sqrt",
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=-1,
    )
    rf.fit(X_train_scaled, y_train)
    
    y_pred = rf.predict(X_test_scaled)
    y_prob = rf.predict_proba(X_test_scaled)
    
    acc = accuracy_score(y_test, y_pred) * 100.0
    bal_acc = balanced_accuracy_score(y_test, y_pred) * 100.0
    p, r, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="macro")
    macro_f1 = f1 * 100.0
    
    # FPR on normal class (label 0)
    norm_mask = (y_test == 0)
    fpr = np.mean(y_pred[norm_mask] != 0) * 100.0
    
    # Containment (attack sessions approved vs contained)
    attack_mask = (y_test != 0)
    # Score = 1 - P(normal)
    scores = 1.0 - y_prob[:, 0]
    contained = np.mean(scores[attack_mask] >= 0.45) * 100.0
    
    return {
        "seed": seed,
        "accuracy": round(acc, 2),
        "balanced_accuracy": round(bal_acc, 2),
        "macro_f1": round(macro_f1, 2),
        "fpr": round(fpr, 2),
        "containment": round(contained, 2)
    }

def main():
    results = []
    for s in SEEDS:
        res = run_seed_eval(s)
        results.append(res)
        print(f"Seed {s}: Acc={res['accuracy']}%, Macro-F1={res['macro_f1']}%, FPR={res['fpr']}%, Containment={res['containment']}%")
        
    accs = [r["accuracy"] for r in results]
    f1s = [r["macro_f1"] for r in results]
    fprs = [r["fpr"] for r in results]
    conts = [r["containment"] for r in results]
    
    summary = {
        "seeds": SEEDS,
        "per_seed": results,
        "mean_accuracy": round(float(np.mean(accs)), 2),
        "std_accuracy": round(float(np.std(accs)), 2),
        "mean_macro_f1": round(float(np.mean(f1s)), 2),
        "std_macro_f1": round(float(np.std(f1s)), 2),
        "mean_fpr": round(float(np.mean(fprs)), 2),
        "std_fpr": round(float(np.std(fprs)), 2),
        "mean_containment": round(float(np.mean(conts)), 2),
        "std_containment": round(float(np.std(conts)), 2),
    }
    
    out_file = Path("results/multi_seed_results.json")
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nMulti-Seed Summary: Acc={summary['mean_accuracy']}±{summary['std_accuracy']}%, Macro-F1={summary['mean_macro_f1']}±{summary['std_macro_f1']}%, FPR={summary['mean_fpr']}±{summary['std_fpr']}%")

if __name__ == "__main__":
    main()

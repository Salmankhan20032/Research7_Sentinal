import argparse
import hashlib
import hmac
import json
import math
import os
import random
import time
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

SEED = 20260724
np.random.seed(SEED)
random.seed(SEED)

CLASSES = [
    "normal",
    "insider_drift",
    "credential_misuse",
    "slow_evasion",
    "privilege_abuse",
    "replay",
]
FEATURES = [
    "op_read",
    "op_write",
    "op_setpoint",
    "value_norm",
    "delta_norm",
    "interarrival_log",
    "hour_sin",
    "hour_cos",
    "role_permission",
    "origin_trust",
    "nonce_fresh",
    "repeat_similarity",
    "cross_sensor_residual",
    "within_safe_envelope",
    "rate_z",
    "session_progress",
    "device_pump",
    "device_valve",
    "device_heater",
]
SEQ_LEN = 48
SUMMARY_STATS = ["mean", "std", "min", "max", "end_minus_start", "slope", "q25", "q75"]


def _profile(rng: np.random.Generator):
    role = int(rng.integers(0, 3))
    device = int(rng.integers(0, 3))
    base = float(np.clip(rng.normal([0.52, 0.48, 0.58][device], 0.09), 0.22, 0.78))
    std = float(rng.uniform(0.012, 0.045))
    cadence = float(rng.lognormal(-0.05, 0.25))
    start_hour = float(rng.uniform(0, 24))
    origin = float(np.clip(rng.normal(0.92, 0.035), 0.72, 0.995))
    write_prob = [0.08, 0.20, 0.34][role]
    setpoint_prob = [0.02, 0.10, 0.22][role]
    return role, device, base, std, cadence, start_hour, origin, write_prob, setpoint_prob


def _choose_op(write_prob: float, setpoint_prob: float, rng: np.random.Generator) -> int:
    u = rng.random()
    return 2 if u < setpoint_prob else (1 if u < setpoint_prob + write_prob else 0)


def generate_session(label: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    role, device, base, std, cadence, start_hour, origin_base, write_prob, setpoint_prob = _profile(rng)
    x = np.zeros((SEQ_LEN, len(FEATURES)), dtype=np.float32)
    attack_start = int(rng.integers(20, 34))
    value = base + rng.normal(0, std)
    prev_op = 0
    repeated_template = None
    cumulative_drift = 0.0
    normal_transient = int(rng.choice([0, 1, 2, 3], p=[0.70, 0.10, 0.12, 0.08])) if label == 0 else 0
    transient_start = int(rng.integers(18, 34))
    transient_len = int(rng.integers(5, 11))

    for t in range(SEQ_LEN):
        progress = t / (SEQ_LEN - 1)
        hour = (start_hour + t * cadence / 3600.0) % 24.0
        op = _choose_op(write_prob, setpoint_prob, rng)
        interarrival = max(0.04, rng.lognormal(math.log(cadence), 0.17))
        role_permission = 1.0
        origin_trust = float(np.clip(origin_base + rng.normal(0, 0.015), 0, 1))
        nonce_fresh = 1.0
        repeat_similarity = float(np.clip(rng.beta(1.2, 11.0), 0, 1))
        cross_residual = abs(float(rng.normal(0.035, 0.018)))
        within_safe_envelope = 1.0
        rate_z = float(rng.normal(0, 0.45))

        target = base + rng.normal(0, std)
        if op in (1, 2):
            target += rng.normal(0, std * 0.7)
        else:
            target = 0.82 * value + 0.18 * target

        # Benign transients deliberately overlap with attack features.
        if label == 0 and transient_start <= t < transient_start + transient_len:
            if normal_transient == 1:
                origin_trust = float(np.clip(rng.normal(0.76, 0.055), 0.58, 0.90))
                rate_z += rng.normal(0.55, 0.30)
                interarrival *= rng.uniform(0.70, 1.15)
            elif normal_transient == 2:
                target += rng.normal(0.025, 0.020)
                cross_residual += abs(rng.normal(0.035, 0.020))
                if rng.random() < 0.28:
                    op = 2
            elif normal_transient == 3:
                repeat_similarity = float(rng.uniform(0.62, 0.90))
                if rng.random() < 0.20:
                    nonce_fresh = 0.0

        if label == 1 and t >= attack_start:  # insider drift
            cumulative_drift += rng.uniform(0.0018, 0.0045)
            target += cumulative_drift
            cross_residual += 0.018 + 0.065 * ((t - attack_start) / max(1, SEQ_LEN - attack_start))
            if rng.random() < 0.20:
                op = 2
            rate_z += rng.normal(0.18, 0.30)
        elif label == 2 and t >= attack_start:  # credential misuse
            origin_trust = float(np.clip(rng.normal(0.74, 0.09), 0.42, 0.92))
            interarrival *= rng.uniform(0.68, 0.95)
            rate_z += rng.normal(0.62, 0.42)
            if rng.random() < 0.16:
                op = 1 if rng.random() < 0.65 else 2
            target += rng.normal(0, std * 1.4)
            if rng.random() < 0.18:
                origin_trust = float(np.clip(rng.normal(0.88, 0.035), 0.72, 0.96))
        elif label == 3 and t >= attack_start:  # slow evasion
            phase = (t - attack_start) / max(1, SEQ_LEN - attack_start)
            cumulative_drift += rng.uniform(0.0010, 0.0029)
            target += cumulative_drift + 0.004 * math.sin(t / 2.7)
            cross_residual += 0.010 + 0.047 * phase
            rate_z += rng.normal(0.05, 0.28)
            if rng.random() < 0.12:
                op = 2
        elif label == 4 and t >= attack_start:  # privilege abuse
            if rng.random() < 0.24:
                op = 2 if rng.random() < 0.70 else 1
                role_permission = 0.0
                target += rng.normal(0.025, 0.028)
            origin_trust = float(np.clip(origin_trust - rng.uniform(0, 0.035), 0, 1))
        elif label == 5 and t >= attack_start:  # replay
            if repeated_template is None:
                repeated_template = (prev_op, value)
            if rng.random() < 0.40:
                op, target = repeated_template
                nonce_fresh = 0.0
                repeat_similarity = float(rng.uniform(0.76, 0.98))
                interarrival *= rng.uniform(0.78, 1.12)
            else:
                repeat_similarity = float(rng.uniform(0.35, 0.76))

        target = float(np.clip(target, 0.02, 0.98))
        if target < 0.08 or target > 0.92:
            within_safe_envelope = 0.0
        delta = target - value
        value = target
        prev_op = op

        x[t, op] = 1.0
        x[t, 3] = value
        x[t, 4] = delta
        x[t, 5] = math.log1p(interarrival)
        x[t, 6] = math.sin(2 * math.pi * hour / 24)
        x[t, 7] = math.cos(2 * math.pi * hour / 24)
        x[t, 8] = role_permission
        x[t, 9] = origin_trust
        x[t, 10] = nonce_fresh
        x[t, 11] = repeat_similarity
        x[t, 12] = cross_residual
        x[t, 13] = within_safe_envelope
        x[t, 14] = rate_z
        x[t, 15] = progress
        x[t, 16 + device] = 1.0

    return x


def generate_dataset(n_sessions: int, path: Path):
    counts = [int(n_sessions * 0.60)] + [int(n_sessions * 0.08)] * 5
    counts[0] += n_sessions - sum(counts)
    y = np.concatenate([np.full(count, i, dtype=np.int64) for i, count in enumerate(counts)])
    np.random.default_rng(SEED).shuffle(y)
    X = np.empty((n_sessions, SEQ_LEN, len(FEATURES)), dtype=np.float32)
    for i, label in enumerate(y):
        X[i] = generate_session(int(label), SEED + i * 17 + int(label) * 100003)
    np.savez_compressed(path, X=X, y=y)
    return X, y


def split_sessions(y: np.ndarray):
    rng = np.random.default_rng(SEED + 99)
    train, validation, test = [], [], []
    for class_id in range(len(CLASSES)):
        indices = np.where(y == class_id)[0]
        rng.shuffle(indices)
        n_train = int(0.70 * len(indices))
        n_validation = int(0.15 * len(indices))
        train.extend(indices[:n_train])
        validation.extend(indices[n_train:n_train + n_validation])
        test.extend(indices[n_train + n_validation:])
    rng.shuffle(train)
    rng.shuffle(validation)
    rng.shuffle(test)
    return np.array(train), np.array(validation), np.array(test)


def harden_test(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Apply a modest held-out domain shift to avoid same-generator optimism."""
    out = X.copy()
    rng = np.random.default_rng(SEED + 707)
    continuous = [3, 4, 5, 6, 7, 9, 11, 12, 14, 15]
    categorical = [0, 1, 2, 8, 10, 13, 16, 17, 18]
    for i, label in enumerate(y):
        if label != 0:
            benign = generate_session(0, SEED + 900000 + i * 31)
            alpha = float(rng.uniform(0.82, 0.94))
            temp = out[i].copy()
            temp[:, continuous] = alpha * X[i][:, continuous] + (1 - alpha) * benign[:, continuous]
            mask = rng.random(SEQ_LEN) < alpha
            for t in range(SEQ_LEN):
                if not mask[t]:
                    temp[t, categorical] = benign[t, categorical]
            cut = int(rng.integers(18, 27))
            temp[:cut] = benign[:cut]
            out[i] = temp
        elif rng.random() < 0.12:
            attack_class = int(rng.integers(1, len(CLASSES)))
            transient = generate_session(attack_class, SEED + 1200000 + i * 43)
            start = int(rng.integers(30, 40))
            alpha = float(rng.uniform(0.08, 0.16))
            temp = out[i, start:].copy()
            temp[:, continuous] = (1 - alpha) * temp[:, continuous] + alpha * transient[start:, continuous]
            mask = rng.random(SEQ_LEN - start) < alpha * 0.55
            for j, t in enumerate(range(start, SEQ_LEN)):
                if mask[j]:
                    temp[j, categorical] = transient[t, categorical]
            out[i, start:] = temp
    return out.astype(np.float32)


def summarize(X: np.ndarray) -> np.ndarray:
    t = np.arange(X.shape[1], dtype=np.float32)
    centered = t - t.mean()
    denominator = float(np.sum(centered ** 2))
    values = [
        X.mean(axis=1),
        X.std(axis=1),
        X.min(axis=1),
        X.max(axis=1),
        X[:, -1] - X[:, 0],
        np.einsum("t,ntf->nf", centered, X) / denominator,
        np.quantile(X, 0.25, axis=1),
        np.quantile(X, 0.75, axis=1),
    ]
    return np.concatenate(values, axis=1).astype(np.float32)


def summary_feature_names():
    names = []
    for stat in SUMMARY_STATS:
        names.extend([f"{feature}:{stat}" for feature in FEATURES])
    return names


def rules_predict(X: np.ndarray):
    pred = np.zeros(len(X), dtype=np.int64)
    role_violation = (X[:, :, 8] < 0.5).mean(axis=1)
    low_origin = (X[:, :, 9] < 0.68).mean(axis=1)
    stale_nonce = (X[:, :, 10] < 0.5).mean(axis=1)
    high_repeat = (X[:, :, 11] > 0.84).mean(axis=1)
    drift = X[:, -1, 3] - X[:, 8:16, 3].mean(axis=1)
    tail_residual = X[:, -12:, 12].mean(axis=1)
    tail_rate = X[:, -12:, 14].mean(axis=1)
    pred[(drift > 0.15) & (tail_residual > 0.105)] = 1
    pred[(low_origin > 0.25) & (tail_rate > 0.60)] = 2
    pred[(drift > 0.085) & (tail_residual > 0.082) & (pred == 0)] = 3
    pred[role_violation > 0.18] = 4
    pred[(stale_nonce > 0.24) & (high_repeat > 0.22)] = 5
    return pred


def metrics_row(name: str, y_true: np.ndarray, y_pred: np.ndarray, probabilities=None):
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    benign = y_true == 0
    row = {
        "model": name,
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "macro_precision": precision,
        "macro_recall": recall,
        "macro_f1": f1,
        "false_positive_rate": float(np.mean(y_pred[benign] != 0)),
    }
    if probabilities is not None:
        binary = (y_true != 0).astype(int)
        score = 1.0 - probabilities[:, 0]
        row["binary_roc_auc"] = roc_auc_score(binary, score)
        row["binary_pr_auc"] = average_precision_score(binary, score)
    else:
        row["binary_roc_auc"] = np.nan
        row["binary_pr_auc"] = np.nan
    return row


def select_thresholds(y_validation: np.ndarray, probabilities: np.ndarray):
    score = 1.0 - probabilities[:, 0]
    attack = y_validation != 0
    best = None
    for clear in np.arange(0.05, 0.51, 0.025):
        for block in np.arange(max(clear + 0.20, 0.50), 0.96, 0.025):
            normal_approval = np.mean(score[~attack] < clear)
            containment = np.mean(score[attack] >= clear)
            false_block = np.mean(score[~attack] >= block)
            immediate_block = np.mean(score[attack] >= block)
            utility = 1.6 * containment + 0.8 * normal_approval + 0.25 * immediate_block - 3.2 * false_block
            if false_block <= 0.02 and (best is None or utility > best[0]):
                best = (utility, float(clear), float(block))
    return (best[1], best[2]) if best else (0.25, 0.80)


def triage_metrics(y_true: np.ndarray, probabilities: np.ndarray, clear: float, block: float):
    score = 1.0 - probabilities[:, 0]
    attack = y_true != 0
    return {
        "tau_clear": clear,
        "tau_block": block,
        "normal_approval_rate": float(np.mean(score[~attack] < clear)),
        "normal_honeypot_rate": float(np.mean((score[~attack] >= clear) & (score[~attack] < block))),
        "normal_false_block_rate": float(np.mean(score[~attack] >= block)),
        "attack_containment_rate": float(np.mean(score[attack] >= clear)),
        "attack_immediate_block_rate": float(np.mean(score[attack] >= block)),
        "attack_missed_rate": float(np.mean(score[attack] < clear)),
    }


def token_tests(n_attempts=14000):
    key = hashlib.sha256(b"sentinel-reference-key").digest()
    used_nonces = set()
    now = int(time.time() * 1000)

    def canonical(context):
        fields = ["worker", "role", "device", "op", "value", "nonce", "issued", "expires", "policy"]
        return "|".join(str(context[field]) for field in fields).encode()

    def issue(context):
        return hmac.new(key, canonical(context), hashlib.sha256).hexdigest()

    def verify(context, token, timestamp):
        if not hmac.compare_digest(issue(context), token):
            return False
        if timestamp > context["expires"] or timestamp < context["issued"] - 200:
            return False
        if context["nonce"] in used_nonces:
            return False
        if context["op"] not in ("write", "setpoint"):
            return False
        if context["role"] not in ("operator", "engineer"):
            return False
        if not 0.08 <= float(context["value"]) <= 0.92:
            return False
        used_nonces.add(context["nonce"])
        return True

    base = {
        "worker": "w17",
        "role": "operator",
        "device": "plc4:pump2",
        "op": "setpoint",
        "value": "0.63",
        "nonce": "valid",
        "issued": now,
        "expires": now + 800,
        "policy": "p7",
    }
    valid = verify(dict(base), issue(base), now + 5)
    cases = ["missing_token", "tampered_value", "expired", "wrong_device", "replay", "unauthorized_role", "unsafe_value"]
    attempts_per_case = n_attempts // len(cases)
    output = {}
    for case in cases:
        accepted = 0
        for i in range(attempts_per_case):
            context = dict(base)
            context["nonce"] = f"{case}-{i}"
            timestamp = now + 10
            token = issue(context)
            if case == "missing_token":
                token = ""
            elif case == "tampered_value":
                token = issue(context)
                context["value"] = "0.77"
            elif case == "expired":
                context["issued"] = now - 2000
                context["expires"] = now - 1200
                token = issue(context)
            elif case == "wrong_device":
                token = issue(context)
                context["device"] = "plc9:heater1"
            elif case == "replay":
                token = issue(context)
                verify(context, token, timestamp)
                accepted += int(verify(context, token, timestamp + 1))
                continue
            elif case == "unauthorized_role":
                context["role"] = "viewer"
                token = issue(context)
            elif case == "unsafe_value":
                context["value"] = "0.97"
                token = issue(context)
            accepted += int(verify(context, token, timestamp))
        output[case] = {
            "attempts": attempts_per_case,
            "accepted": accepted,
            "rejected": attempts_per_case - accepted,
        }
    return {"valid_command_accepted": bool(valid), "unauthorized_cases": output}


def benchmark_classifier(model, scaler, raw_session: np.ndarray, sample: np.ndarray, n=1000):
    sample = sample.reshape(1, -1)
    old_n_jobs = getattr(model, "n_jobs", None)
    if old_n_jobs is not None:
        model.n_jobs = 1
    for _ in range(20):
        model.predict_proba(sample)
    latency = []
    for _ in range(n):
        start = time.perf_counter_ns()
        model.predict_proba(sample)
        latency.append((time.perf_counter_ns() - start) / 1e6)

    # Full in-process path: 48-command feature aggregation, scaling, and inference.
    raw_session = raw_session.reshape(1, SEQ_LEN, len(FEATURES))
    for _ in range(20):
        model.predict_proba(scaler.transform(summarize(raw_session)))
    full_path_latency = []
    for _ in range(n):
        start = time.perf_counter_ns()
        model.predict_proba(scaler.transform(summarize(raw_session)))
        full_path_latency.append((time.perf_counter_ns() - start) / 1e6)

    key = hashlib.sha256(b"bench").digest()
    payload = b"w17|pump2|setpoint|.63|nonce|time"
    hmac_latency = []
    for _ in range(n):
        start = time.perf_counter_ns()
        token = hmac.new(key, payload, hashlib.sha256).digest()
        hmac.compare_digest(token, hmac.new(key, payload, hashlib.sha256).digest())
        hmac_latency.append((time.perf_counter_ns() - start) / 1e6)

    def quantiles(values):
        values = np.array(values)
        return {
            "p50": float(np.percentile(values, 50)),
            "p95": float(np.percentile(values, 95)),
            "p99": float(np.percentile(values, 99)),
            "mean": float(values.mean()),
        }

    result = {
        "benchmark_iterations": n,
        "scorer_inference_ms": quantiles(latency),
        "full_feature_scaling_scorer_ms": quantiles(full_path_latency),
        "hmac_issue_verify_ms": quantiles(hmac_latency),
    }
    if old_n_jobs is not None:
        model.n_jobs = old_n_jobs
    return result


def make_figures(out_dir: Path, metrics_df: pd.DataFrame, y_test, prediction, probabilities, triage, model, feature_names):
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    positions = np.arange(len(metrics_df))
    width = 0.24
    ax.bar(positions - width, metrics_df["accuracy"] * 100, width, label="Accuracy")
    ax.bar(positions, metrics_df["macro_f1"] * 100, width, label="Macro-F1")
    ax.bar(positions + width, metrics_df["balanced_accuracy"] * 100, width, label="Balanced accuracy")
    ax.set_xticks(positions, metrics_df["model"], rotation=18, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "model_comparison.pdf", bbox_inches="tight")
    fig.savefig(out_dir / "model_comparison.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    _, recall, _, _ = precision_recall_fscore_support(
        y_test, prediction, labels=np.arange(len(CLASSES)), zero_division=0
    )
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.bar(CLASSES, recall * 100)
    ax.set_ylabel("Recall (%)")
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", rotation=23)
    ax.grid(axis="y", alpha=0.25)
    for i, value in enumerate(recall * 100):
        ax.text(i, value + 1.2, f"{value:.1f}", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "per_class_recall.pdf", bbox_inches="tight")
    fig.savefig(out_dir / "per_class_recall.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    matrix = confusion_matrix(y_test, prediction, normalize="true")
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    image = ax.imshow(matrix, vmin=0, vmax=1, cmap="Blues")
    ax.set_xticks(range(len(CLASSES)), CLASSES, rotation=35, ha="right")
    ax.set_yticks(range(len(CLASSES)), CLASSES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            ax.text(
                j,
                i,
                f"{matrix[i, j] * 100:.0f}",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if matrix[i, j] > 0.55 else "black",
            )
    fig.colorbar(image, ax=ax, label="Row-normalized rate")
    fig.tight_layout()
    fig.savefig(out_dir / "confusion_matrix.pdf", bbox_inches="tight")
    fig.savefig(out_dir / "confusion_matrix.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    score = 1.0 - probabilities[:, 0]
    attack = y_test != 0
    thresholds = np.linspace(0.02, 0.98, 80)
    normal_approval = [np.mean(score[~attack] < threshold) for threshold in thresholds]
    attack_containment = [np.mean(score[attack] >= threshold) for threshold in thresholds]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(thresholds, np.array(normal_approval) * 100, label="Normal approval")
    ax.plot(thresholds, np.array(attack_containment) * 100, label="Attack containment")
    ax.axvline(triage["tau_clear"], linestyle="--", label="clear threshold")
    ax.axvline(triage["tau_block"], linestyle=":", label="block threshold")
    ax.set_xlabel("Maliciousness-score threshold")
    ax.set_ylabel("Rate (%)")
    ax.set_ylim(0, 101)
    ax.grid(alpha=0.25)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "triage_tradeoff.pdf", bbox_inches="tight")
    fig.savefig(out_dir / "triage_tradeoff.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    if hasattr(model, "feature_importances_"):
        importance = np.asarray(model.feature_importances_)
        top = np.argsort(importance)[-12:][::-1]
        labels = [feature_names[index] for index in top]
        values = importance[top]
        fig, ax = plt.subplots(figsize=(7.2, 4.4))
        order = np.arange(len(top))[::-1]
        ax.barh(order, values[::-1])
        ax.set_yticks(order, labels[::-1])
        ax.set_xlabel("Random-forest importance")
        ax.grid(axis="x", alpha=0.25)
        fig.tight_layout()
        fig.savefig(out_dir / "feature_importance.pdf", bbox_inches="tight")
        fig.savefig(out_dir / "feature_importance.png", dpi=220, bbox_inches="tight")
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=4000)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root
    results_dir = root / "results"
    figures_dir = root / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)

    X, y = generate_dataset(args.sessions, results_dir / "synthetic_sessions.npz")
    train_idx, validation_idx, test_idx = split_sessions(y)
    X_train = X[train_idx]
    X_validation = X[validation_idx]
    X_test = harden_test(X[test_idx], y[test_idx])
    y_train, y_validation, y_test = y[train_idx], y[validation_idx], y[test_idx]

    train_summary = summarize(X_train)
    validation_summary = summarize(X_validation)
    test_summary = summarize(X_test)
    scaler = StandardScaler().fit(train_summary)
    S_train = scaler.transform(train_summary)
    S_validation = scaler.transform(validation_summary)
    S_test = scaler.transform(test_summary)

    results = []
    predictions = {}
    probabilities = {}

    rule_prediction = rules_predict(X_test)
    results.append(metrics_row("Rules only", y_test, rule_prediction))
    predictions["Rules only"] = rule_prediction

    logistic = LogisticRegression(max_iter=700, class_weight="balanced", C=1.2)
    logistic.fit(S_train, y_train)
    prediction = logistic.predict(S_test)
    probability = logistic.predict_proba(S_test)
    results.append(metrics_row("Logistic regression", y_test, prediction, probability))
    predictions["Logistic regression"] = prediction
    probabilities["Logistic regression"] = probability

    hgb = HistGradientBoostingClassifier(
        max_iter=180,
        learning_rate=0.07,
        max_leaf_nodes=25,
        l2_regularization=0.15,
        class_weight="balanced",
        random_state=SEED,
    )
    hgb.fit(S_train, y_train)
    prediction = hgb.predict(S_test)
    probability = hgb.predict_proba(S_test)
    results.append(metrics_row("Gradient boosting", y_test, prediction, probability))
    predictions["Gradient boosting"] = prediction
    probabilities["Gradient boosting"] = probability

    random_forest = RandomForestClassifier(
        n_estimators=160,
        max_depth=15,
        min_samples_leaf=3,
        class_weight="balanced_subsample",
        random_state=SEED,
        n_jobs=-1,
        max_features="sqrt",
    )
    random_forest.fit(S_train, y_train)
    prediction = random_forest.predict(S_test)
    probability = random_forest.predict_proba(S_test)
    results.append(metrics_row("SENTINEL scorer", y_test, prediction, probability))
    predictions["SENTINEL scorer"] = prediction
    probabilities["SENTINEL scorer"] = probability

    metrics_df = pd.DataFrame(results)
    metrics_df.to_csv(results_dir / "model_metrics.csv", index=False)

    per_class_rows = []
    for model_name, model_prediction in predictions.items():
        precision, recall, f1, support = precision_recall_fscore_support(
            y_test,
            model_prediction,
            labels=np.arange(len(CLASSES)),
            zero_division=0,
        )
        for class_id, class_name in enumerate(CLASSES):
            per_class_rows.append(
                {
                    "model": model_name,
                    "class": class_name,
                    "precision": precision[class_id],
                    "recall": recall[class_id],
                    "f1": f1[class_id],
                    "support": int(support[class_id]),
                }
            )
    pd.DataFrame(per_class_rows).to_csv(results_dir / "per_class_metrics.csv", index=False)

    validation_probability = random_forest.predict_proba(S_validation)
    clear, block = select_thresholds(y_validation, validation_probability)
    triage = triage_metrics(y_test, probability, clear, block)
    with open(results_dir / "triage_metrics.json", "w") as file:
        json.dump(triage, file, indent=2)

    token_result = token_tests()
    with open(results_dir / "token_tests.json", "w") as file:
        json.dump(token_result, file, indent=2)

    latency = benchmark_classifier(random_forest, scaler, X_test[0], S_test[0])
    with open(results_dir / "latency_benchmark.json", "w") as file:
        json.dump(latency, file, indent=2)
    with open(results_dir / "pipeline_latency.json", "w") as file:
        json.dump(latency["full_feature_scaling_scorer_ms"], file, indent=2)

    feature_names = summary_feature_names()

    # Save test predictions and confusion matrix for downstream plotting scripts
    np.savez(
        results_dir / "test_predictions.npz",
        y_true=y_test,
        y_pred=prediction,
        probabilities=probability,
        maliciousness_scores=1.0 - probability[:, 0], # 1 - P(normal)
    )

    cm = confusion_matrix(y_test, prediction, labels=np.arange(len(CLASSES)))
    cm_df = pd.DataFrame(cm, index=CLASSES, columns=CLASSES)
    cm_df.to_csv(results_dir / "confusion_counts.csv")

    joblib.dump(
        {"model": random_forest, "scaler": scaler, "feature_names": feature_names, "classes": CLASSES},
        results_dir / "sentinel_scorer.joblib",
    )

    manifest = {
        "seed": SEED,
        "sessions": int(len(y)),
        "commands": int(len(y) * SEQ_LEN),
        "sequence_length": SEQ_LEN,
        "feature_count": len(FEATURES),
        "features": FEATURES,
        "summary_dimension": len(feature_names),
        "split_unit": "complete session",
        "test_shift": "later attack onset, benign-profile mixing, and maintenance-like benign transients",
        "class_counts_total": {CLASSES[i]: int(np.sum(y == i)) for i in range(len(CLASSES))},
        "class_counts_train": {CLASSES[i]: int(np.sum(y_train == i)) for i in range(len(CLASSES))},
        "class_counts_validation": {CLASSES[i]: int(np.sum(y_validation == i)) for i in range(len(CLASSES))},
        "class_counts_test": {CLASSES[i]: int(np.sum(y_test == i)) for i in range(len(CLASSES))},
    }
    with open(results_dir / "dataset_manifest.json", "w") as file:
        json.dump(manifest, file, indent=2)

    make_figures(
        figures_dir,
        metrics_df,
        y_test,
        prediction,
        probability,
        triage,
        random_forest,
        feature_names,
    )

    summary = {
        "dataset": manifest,
        "metrics": results,
        "triage": triage,
        "token_tests": token_result,
        "latency": latency,
    }
    with open(results_dir / "summary.json", "w") as file:
        json.dump(summary, file, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

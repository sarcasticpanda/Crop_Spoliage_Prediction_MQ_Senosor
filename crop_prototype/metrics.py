from __future__ import annotations
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, log_loss, confusion_matrix, classification_report

LABELS = ["acceptable", "warning", "spoiled"]

def summarize(y_true, y_pred, probabilities, crops, groups):
    return {
        "rows": int(len(y_true)), "independent_lots": int(len(set(groups))),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        # sklearn expects labels in lexicographic order; reorder probability columns accordingly.
        "log_loss": float(log_loss(y_true, probabilities[:, [0, 2, 1]], labels=sorted(LABELS))),
        "multiclass_brier": float(np.mean(np.sum((probabilities - np.eye(len(LABELS))[np.array([LABELS.index(v) for v in y_true])])**2, axis=1))),
        "confusion_matrix_labels_order": LABELS,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
        "per_class": classification_report(y_true, y_pred, labels=LABELS, output_dict=True, zero_division=0),
        "per_crop": {str(c): {
            "rows": int(sum(np.asarray(crops) == c)),
            "macro_f1": float(f1_score(np.asarray(y_true)[np.asarray(crops) == c], np.asarray(y_pred)[np.asarray(crops) == c], labels=LABELS, average="macro", zero_division=0)),
            "per_class": classification_report(np.asarray(y_true)[np.asarray(crops) == c], np.asarray(y_pred)[np.asarray(crops) == c], labels=LABELS, output_dict=True, zero_division=0),
        } for c in sorted(set(crops))},
    }

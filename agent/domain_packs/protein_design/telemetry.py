"""Biological KPI helpers for protein binder design."""

from __future__ import annotations

from statistics import mean
from typing import Any


def summarize_validation_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize terminal filter metrics for generated candidates."""
    if not candidates:
        return {
            "candidate_count": 0,
            "passing_count": 0,
            "mean_iptm": None,
            "mean_plddt": None,
            "fold_clusters": 0,
        }

    iptm_values = [
        float(item["iptm"]) for item in candidates if item.get("iptm") is not None
    ]
    plddt_values = [
        float(item["plddt"]) for item in candidates if item.get("plddt") is not None
    ]
    passing = [
        item
        for item in candidates
        if float(item.get("iptm") or 0.0) > 0.8
        and float(item.get("plddt") or 0.0) > 80.0
    ]
    clusters = {
        item.get("fold_cluster") for item in passing if item.get("fold_cluster")
    }
    return {
        "candidate_count": len(candidates),
        "passing_count": len(passing),
        "mean_iptm": round(mean(iptm_values), 4) if iptm_values else None,
        "mean_plddt": round(mean(plddt_values), 2) if plddt_values else None,
        "fold_clusters": len(clusters),
    }

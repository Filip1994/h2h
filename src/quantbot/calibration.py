from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from .types import Market


def _clip_probability(value: float) -> float:
    return min(1.0 - 1e-8, max(1e-8, value))


@dataclass(frozen=True, slots=True)
class CalibrationParameters:
    a: float
    b: float
    n: int
    validated: bool
    method: str


class ProbabilityCalibrator:
    def __init__(
        self, parameters: dict[Market, CalibrationParameters], min_samples: int = 200
    ) -> None:
        self.parameters = parameters
        self.min_samples = min_samples

    @classmethod
    def load(cls, path: Path, min_samples: int = 200) -> ProbabilityCalibrator:
        if not path.exists():
            return cls({}, min_samples=min_samples)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path} nije validan calibration JSON") from exc
        parameters: dict[Market, CalibrationParameters] = {}
        for key, value in raw.items():
            try:
                market = Market(key)
                parameters[market] = CalibrationParameters(
                    a=float(value["a"]),
                    b=float(value["b"]),
                    n=int(value["n"]),
                    validated=bool(value.get("validated", False)),
                    method=str(value.get("method", "PLATT")),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return cls(parameters, min_samples=min_samples)

    def is_validated(self, market: Market) -> bool:
        params = self.parameters.get(market)
        return params is not None and params.validated and params.n >= self.min_samples

    def apply(self, market: Market, probability: float) -> tuple[float, str]:
        probability = _clip_probability(probability)
        params = self.parameters.get(market)
        if params is None or not params.validated or params.n < self.min_samples:
            return probability, "IDENTITY_UNVALIDATED"
        logit = math.log(probability / (1.0 - probability))
        calibrated = 1.0 / (1.0 + math.exp(-(params.a * logit + params.b)))
        return _clip_probability(calibrated), f"{params.method}_N_{params.n}"


def _fit_platt(probabilities: np.ndarray, outcomes: np.ndarray) -> tuple[float, float]:
    logits = np.log(
        np.clip(probabilities, 1e-8, 1.0 - 1e-8)
        / np.clip(1.0 - probabilities, 1e-8, 1.0)
    )

    def objective(params: np.ndarray) -> float:
        scores = np.clip(params[0] * logits + params[1], -30.0, 30.0)
        calibrated = 1.0 / (1.0 + np.exp(-scores))
        loss = -np.mean(
            outcomes * np.log(np.clip(calibrated, 1e-10, 1.0))
            + (1.0 - outcomes) * np.log(np.clip(1.0 - calibrated, 1e-10, 1.0))
        )
        return float(loss + 1e-4 * ((params[0] - 1.0) ** 2 + params[1] ** 2))

    result = minimize(
        objective,
        np.asarray([1.0, 0.0]),
        method="L-BFGS-B",
        bounds=[(0.05, 5.0), (-5.0, 5.0)],
    )
    if not result.success:
        return 1.0, 0.0
    return float(result.x[0]), float(result.x[1])


def _apply_array(probabilities: np.ndarray, a: float, b: float) -> np.ndarray:
    logits = np.log(
        np.clip(probabilities, 1e-8, 1.0 - 1e-8)
        / np.clip(1.0 - probabilities, 1e-8, 1.0)
    )
    scores = np.clip(a * logits + b, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-scores))


def _brier(probabilities: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((probabilities - outcomes) ** 2))


def _log_loss(probabilities: np.ndarray, outcomes: np.ndarray) -> float:
    probabilities = np.clip(probabilities, 1e-10, 1.0 - 1e-10)
    return float(
        -np.mean(
            outcomes * np.log(probabilities)
            + (1.0 - outcomes) * np.log(1.0 - probabilities)
        )
    )


def _expected_calibration_error(
    probabilities: np.ndarray, outcomes: np.ndarray, bins: int = 10
) -> float:
    total = len(probabilities)
    if total == 0:
        return 1.0
    error = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (
            (probabilities >= lower) & (probabilities < upper)
            if index < bins - 1
            else (probabilities >= lower) & (probabilities <= upper)
        )
        count = int(np.sum(mask))
        if count:
            error += (count / total) * abs(
                float(np.mean(probabilities[mask])) - float(np.mean(outcomes[mask]))
            )
    return error


def refit_calibration(
    predictions_path: Path,
    output_path: Path,
    min_samples: int = 200,
    max_ece: float = 0.05,
    preserve_existing: bool = True,
) -> dict[str, dict[str, float | int | bool | str]]:
    if not predictions_path.exists():
        return {}
    raw_predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    existing: dict[str, dict[str, float | int | bool | str]] = {}
    if preserve_existing and output_path.exists():
        try:
            loaded = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            existing = {}
    output: dict[str, dict[str, float | int | bool | str]] = {}

    for market in Market:
        rows = [
            row
            for row in raw_predictions
            if row.get("market") == market.value
            and row.get("status") == "SETTLED"
            and row.get("outcome") in {0, 1}
        ]
        rows.sort(key=lambda row: str(row.get("kickoff") or ""))
        n = len(rows)
        if n < min_samples or len({int(row["outcome"]) for row in rows}) < 2:
            prior = existing.get(market.value)
            if isinstance(prior, dict) and prior.get("validated") is True:
                output[market.value] = {**prior, "retained_pending_new_sample": n}
            else:
                output[market.value] = {
                    "a": 1.0,
                    "b": 0.0,
                    "n": n,
                    "validated": False,
                }
            continue

        probabilities = np.asarray(
            [float(row["model_probability"]) for row in rows], dtype=float
        )
        outcomes = np.asarray([int(row["outcome"]) for row in rows], dtype=float)
        split = max(1, int(0.70 * n))
        train_p, validation_p = probabilities[:split], probabilities[split:]
        train_y, validation_y = outcomes[:split], outcomes[split:]
        if len(validation_p) < 50 or len(set(validation_y.tolist())) < 2:
            prior = existing.get(market.value)
            if isinstance(prior, dict) and prior.get("validated") is True:
                output[market.value] = {**prior, "retained_pending_new_sample": n}
            else:
                output[market.value] = {
                    "a": 1.0,
                    "b": 0.0,
                    "n": n,
                    "validated": False,
                }
            continue

        a_train, b_train = _fit_platt(train_p, train_y)
        calibrated_validation = _apply_array(validation_p, a_train, b_train)
        raw_brier = _brier(validation_p, validation_y)
        calibrated_brier = _brier(calibrated_validation, validation_y)
        raw_log_loss = _log_loss(validation_p, validation_y)
        calibrated_log_loss = _log_loss(calibrated_validation, validation_y)
        platt_accepted = (
            calibrated_brier <= raw_brier and calibrated_log_loss <= raw_log_loss
        )
        chosen_validation = calibrated_validation if platt_accepted else validation_p
        validation_ece = _expected_calibration_error(chosen_validation, validation_y)
        validated = validation_ece <= max_ece
        a_final, b_final = (
            _fit_platt(probabilities, outcomes)
            if validated and platt_accepted
            else (1.0, 0.0)
        )
        output[market.value] = {
            "a": round(a_final, 8),
            "b": round(b_final, 8),
            "n": n,
            "validated": validated,
            "method": "PLATT" if validated and platt_accepted else "IDENTITY",
            "validation_n": len(validation_p),
            "validation_ece": round(validation_ece, 8),
            "raw_brier": round(raw_brier, 8),
            "calibrated_brier": round(calibrated_brier, 8),
            "raw_log_loss": round(raw_log_loss, 8),
            "calibrated_log_loss": round(calibrated_log_loss, 8),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(output, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return output

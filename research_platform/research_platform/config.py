"""Experiment configuration: loading, validation, and run planning.

A config file is a JSON document that fully describes a family of
experiments: hypothesis, objective, author, the experiment module to
execute, its parameters, an optional dataset reference, and an optional
parameter sweep plus a set of seeds.

The runner materializes one atomic experiment per (parameter set, seed)
pair in a deterministic order, so a given config always produces the
same experiments.

Example config::

    {
      "hypothesis": "H-EXM-01",
      "objective": "Measure the Sharpe of the signal across thresholds",
      "author": "sebastian",
      "assumptions": ["momentum persists", "returns iid"],
      "tags": ["momentum", "daily"],
      "experiment": {
        "module": "examples.experiments.momentum_scan",
        "function": "run",
        "parameters": {"lookback": 20, "threshold": 1.5, "q": 4},
        "dataset": "es-daily-v1"
      },
      "sweep": {"parameter": "threshold", "values": [1.0, 1.5, 2.0]},
      "repeats": 3
    }

Determinism contract
    * ``seeds`` (explicit list) or ``repeats`` (R: seeds 0..R-1) —
      both at once is an error.
    * Sweep values are iterated in the order given in ``values``.
    * Repeat index i uses seed ``seeds[i]`` (repeats: seed i).
    * Sweep + repeats is allowed: for every sweep value, every seed.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import ValidationError, is_canonical_hypothesis_id
from ._util import to_json_safe

REQUIRED_TOP_LEVEL = ("hypothesis", "objective", "author", "experiment")


@dataclass
class PlanItem:
    """One atomic execution: a frozen parameter set plus a seed."""

    params: Dict[str, Any]
    seed: int
    sweep_parameter: Optional[str]
    sweep_value: Optional[Any]
    repeat_index: int


class ExperimentConfig:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.hypothesis = str(raw.get("hypothesis", "")).strip()
        self.objective = str(raw.get("objective", "")).strip()
        self.author = str(raw.get("author", "")).strip()
        self.assumptions = [str(a) for a in raw.get("assumptions", [])]
        self.tags = [str(t) for t in raw.get("tags", [])]
        self.module = str(raw.get("experiment", {}).get("module", ""))
        self.function = str(raw.get("experiment", {}).get("function", "run"))
        self.parameters: Dict[str, Any] = dict(
            raw.get("experiment", {}).get("parameters", {})
        )
        self.dataset_ref: Optional[str] = raw.get("experiment", {}).get("dataset")
        self.sweep_parameter: Optional[str] = None
        self.sweep_values: List[Any] = []
        sweep = raw.get("sweep")
        if sweep is not None:
            if not isinstance(sweep, dict):
                raise ValidationError("'sweep' must be an object or null")
            self.sweep_parameter = sweep.get("parameter")
            self.sweep_values = list(sweep.get("values", []))
        if "seeds" in raw and "repeats" in raw:
            raise ValidationError("config must declare either 'seeds' or 'repeats', not both")
        if "seeds" in raw:
            self.seeds: List[int] = [int(s) for s in raw["seeds"]]
        else:
            n = int(raw.get("repeats", 1))
            self.seeds = list(range(n))
        self.validate()

    # ------------------------------------------------------------------

    def validate(self) -> None:
        missing = [k for k in REQUIRED_TOP_LEVEL if not self.raw.get(k)]
        if missing:
            raise ValidationError("config missing required keys: %s" % ", ".join(missing))
        if not is_canonical_hypothesis_id(self.hypothesis):
            raise ValidationError(
                "config 'hypothesis' must be a canonical catalog ID "
                "(pattern H-XXX-NN, e.g. 'H-MS-01'); got %r" % self.hypothesis
            )
        if not isinstance(self.raw.get("experiment"), dict):
            raise ValidationError("'experiment' must be an object")
        if not str(self.module).strip():
            raise ValidationError("'experiment.module' must be a module import path")
        if self.sweep_parameter is not None:
            if not str(self.sweep_parameter).strip():
                raise ValidationError("'sweep.parameter' must be a parameter name")
            if not self.sweep_values:
                raise ValidationError("'sweep.values' must be a non-empty list")
            for v in self.sweep_values:
                try:
                    to_json_safe(v)  # raises for non-JSON-safe sweep values
                except Exception as exc:  # noqa: BLE001
                    raise ValidationError(
                        "sweep value is not JSON-safe: %s" % exc
                    )
        for s in self.seeds:
            if not isinstance(s, int) or isinstance(s, bool) or s < 0:
                raise ValidationError("seeds must be non-negative integers")
        if "seed" in self.parameters:
            raise ValidationError(
                "parameters must not declare 'seed': seeds are declared at the "
                "config top level ('seeds' or 'repeats')"
            )

    @property
    def has_sweep(self) -> bool:
        return self.sweep_parameter is not None

    @property
    def experiment_count(self) -> int:
        n = len(self.seeds)
        if self.has_sweep:
            n *= len(self.sweep_values)
        return n

    # ------------------------------------------------------------------

    def plan(self) -> List[PlanItem]:
        """Materialize the atomic executions in deterministic order."""
        plan: List[PlanItem] = []
        if self.has_sweep:
            for sweep_value in self.sweep_values:
                for repeat_index, seed in enumerate(self.seeds):
                    params = dict(self.parameters)
                    params[self.sweep_parameter] = sweep_value
                    plan.append(
                        PlanItem(
                            params=params,
                            seed=seed,
                            sweep_parameter=self.sweep_parameter,
                            sweep_value=sweep_value,
                            repeat_index=repeat_index,
                        )
                    )
        else:
            for repeat_index, seed in enumerate(self.seeds):
                plan.append(
                    PlanItem(
                        params=dict(self.parameters),
                        seed=seed,
                        sweep_parameter=None,
                        sweep_value=None,
                        repeat_index=repeat_index,
                    )
                )
        return plan

    def to_document(self) -> Dict[str, Any]:
        """The canonical, re-parseable config document (for storage)."""
        return {
            "hypothesis": self.hypothesis,
            "objective": self.objective,
            "author": self.author,
            "assumptions": self.assumptions,
            "tags": self.tags,
            "experiment": {
                "module": self.module,
                "function": self.function,
                "parameters": self.parameters,
                "dataset": self.dataset_ref,
            },
            "sweep": (
                {"parameter": self.sweep_parameter, "values": self.sweep_values}
                if self.has_sweep
                else None
            ),
            "seeds": self.seeds,
        }

    def resolve_dataset(self, store) -> Optional[str]:
        """Resolve the dataset reference to a registry id (or None)."""
        if self.dataset_ref is None:
            return None
        return store.get_dataset(self.dataset_ref).id


def load_config(path: str) -> ExperimentConfig:
    p = Path(path)
    if not p.is_file():
        raise ValidationError("config file not found: %s" % p)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("config file is not valid JSON: %s" % exc)
    if not isinstance(raw, dict):
        raise ValidationError("config must be a JSON object")
    return ExperimentConfig(raw)

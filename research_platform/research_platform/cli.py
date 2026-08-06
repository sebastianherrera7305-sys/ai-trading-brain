"""Command-line interface: the ``research`` console script.

Every command prints a single JSON document to stdout (human and
machine readable, trivially pipeable into jq). No third-party
dependencies.

Subcommands
    init [root]
        Bootstrap a research store (default: $RESEARCH_HOME or
        ~/.research). Safe to run repeatedly.

    dataset register FILE --source --provider --version --symbol
                  --timeframe --timezone [--name --pipeline
                  --feature-version --meta]
        Register a data file as an immutable dataset.

    dataset list
        List registered datasets.

    dataset verify REF
        Prove the stored blob still hashes to the registered
        checksum.

    dataset show REF
        Show a dataset's manifest.

    run CONFIG.json [--repeats N --seed N --cwd DIR --quiet]
        Execute every atomic experiment implied by a config file.
        ``run EXPERIMENT_UUID`` (with --reproduce) re-executes an
        existing experiment and reports reproducibility.

    status UUID
        Show an experiment's record.

    results UUID [--run N]
        Show the latest (or a specific) run's recorded results.

    compare best --metric M [--direction min --tag T --assumption A
                  --sweep-id H --author NAME --limit 10]
    compare significance --group-a REF --group-b REF --metric M
                  [--permutations 10000 --seed 0]
    compare robustness --metric M --parameter P [--threshold T
                  --direction min --sweep-id H --tag T]
    compare failures [--limit 20]
    compare alpha-by-assumption --metric M [--direction min --tag T]

    audit UUID
        Static reproducibility audit (no re-execution).

    reproduce UUID [--force --cwd DIR]
        Reproduce an experiment: audit inputs, re-execute, verify.
"""

import argparse
import json
import sys
from typing import Any, Dict, Optional

from ._util import read_json
from .compare import (
    alpha_by_assumption,
    best,
    failures,
    robustness,
    significance,
)
from .reproduce import audit as reproduce_audit
from .reproduce import reproduce
from .runner import run_config
from .store import open_store


def _print(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _error(message: str) -> int:
    _print({"error": message})
    return 1


def cmd_init(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    _print({
        "ok": True,
        "root": str(store.root),
        "database": str(store.db_path),
        "datasets": str(store.datasets_dir),
        "experiments": str(store.experiments_dir),
    })
    store.close()
    return 0


def cmd_dataset_register(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        rec = store.register_dataset(
            args.file,
            source=args.source,
            provider=args.provider,
            version=args.version,
            symbol=args.symbol,
            timeframe=args.timeframe,
            timezone=args.timezone,
            name=args.name,
            pipeline=args.pipeline or "",
            feature_version=args.feature_version or "",
            meta=read_json(args.meta) if args.meta else None,
        )
        _print({
            "ok": True,
            "id": rec.id,
            "checksum": rec.checksum,
            "bytes": rec.total_bytes,
            "manifest": str(store.datasets_dir / rec.id / "manifest.json"),
        })
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error("dataset registration failed: %s" % exc)
    finally:
        store.close()


def cmd_dataset_list(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    rows = [{
        "id": d.id, "name": d.name, "source": d.source, "provider": d.provider,
        "version": d.version, "symbol": d.symbol, "timeframe": d.timeframe,
        "timezone": d.timezone, "checksum": d.checksum[:12],
        "bytes": d.total_bytes, "created_at": d.created_at,
    } for d in store.list_datasets()]
    store.close()
    _print({"datasets": rows})
    return 0


def cmd_dataset_verify(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        _print(store.verify_dataset(args.ref))
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    finally:
        store.close()


def cmd_dataset_show(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        _print(store.get_dataset(args.ref).manifest())
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    finally:
        store.close()


def cmd_run(args: argparse.Namespace) -> int:
    if args.repeats is not None or args.seed is not None:
        return _error(
            "--repeats/--seed are not runtime overrides (they would break "
            "config-hash determinism); edit the config file's 'seeds' or "
            "'repeats' field instead"
        )
    store = open_store(args.root)
    try:
        summary = run_config(store, args.config)
        _print(summary)
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error("run failed: %s" % exc)
    finally:
        store.close()


def cmd_status(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        rec = store.get_experiment(args.uuid)
        _print({
            "uuid": rec.uuid,
            "hypothesis": rec.hypothesis,
            "objective": rec.objective,
            "author": rec.author,
            "status": rec.status,
            "created_at": rec.created_at,
            "started_at": rec.started_at,
            "finished_at": rec.finished_at,
            "runtime_seconds": rec.runtime_seconds,
            "failure_reason": rec.failure_reason,
            "config_hash": rec.config_hash,
            "dataset_id": rec.dataset_id,
            "module": rec.module,
            "function": rec.function,
            "module_checksum": rec.module_checksum,
            "seed": rec.seed,
            "params": rec.params,
            "assumptions": rec.assumptions,
            "tags": rec.tags,
            "sweep_id": rec.sweep_id,
            "sweep_parameter": rec.sweep_parameter,
            "sweep_value": rec.sweep_value,
            "repeat_index": rec.repeat_index,
            "git": (
                {"commit": rec.git_commit, "repo": rec.git_repo, "dirty": rec.git_dirty}
                if rec.git_commit else None
            ),
        })
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    finally:
        store.close()


def cmd_results(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        runs = store.get_runs(args.uuid)
        if not runs:
            return _error("no runs recorded for %s" % args.uuid)
        run = next((r for r in runs if r.run_number == args.run), None) if args.run else runs[-1]
        if run is None:
            return _error("no run %d for %s" % (args.run, args.uuid))
        _print({
            "uuid": args.uuid,
            "run_number": run.run_number,
            "status": run.status,
            "result_checksum": run.result_checksum,
            "metrics": run.metrics,
            "tests": run.tests,
            "artifacts": run.artifacts,
            "env": run.env,
            "runtime_seconds": run.runtime_seconds,
            "failure_reason": run.failure_reason,
            "log_path": run.log_path,
        })
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    finally:
        store.close()


def cmd_reproduce(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        _print(reproduce(store, args.uuid, cwd=args.cwd, force=args.force))
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    finally:
        store.close()


def cmd_audit(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        _print(reproduce_audit(store, args.uuid, cwd=args.cwd))
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    finally:
        store.close()


def cmd_compare(args: argparse.Namespace) -> int:
    store = open_store(args.root)
    try:
        kind = args.question
        common: Dict[str, Any] = {}
        if kind == "best":
            _print(best(
                store,
                args.metric,
                direction=args.direction,
                tag=args.tag,
                assumption=args.assumption,
                sweep_id=args.sweep_id,
                author=args.author,
                limit=args.limit,
            ))
        elif kind == "significance":
            _print(significance(
                store,
                args.group_a, args.group_b, args.metric,
                n_permutations=args.permutations, seed=args.seed,
            ))
        elif kind == "robustness":
            _print(robustness(
                store,
                args.metric, args.parameter,
                threshold=args.threshold, direction=args.direction,
                sweep_id=args.sweep_id, tag=args.tag,
            ))
        elif kind == "failures":
            _print(failures(store, limit=args.limit))
        elif kind in ("alpha_by_assumption", "alpha-by-assumption"):
            _print(alpha_by_assumption(
                store,
                args.metric, direction=args.direction, tag=args.tag,
            ))
        else:
            return _error("unknown compare question: %s" % kind)
        return 0
    except Exception as exc:  # noqa: BLE001
        return _error(str(exc))
    finally:
        store.close()


def _add_compare_parser(sub: argparse._SubParsersAction, parent) -> None:
    p = sub.add_parser("compare", parents=[parent], help="comparison engine questions")
    q = p.add_subparsers(dest="question", required=True)

    pb = q.add_parser("best", parents=[parent], help="rank parameter groups by median")
    pb.add_argument("--metric", required=True)
    pb.add_argument("--direction", choices=["max", "min"], default="max")
    pb.add_argument("--tag")
    pb.add_argument("--assumption")
    pb.add_argument("--sweep-id")
    pb.add_argument("--author")
    pb.add_argument("--limit", type=int, default=10)

    ps = q.add_parser("significance", parents=[parent], help="two-sample permutation test")
    ps.add_argument("--group-a", required=True)
    ps.add_argument("--group-b", required=True)
    ps.add_argument("--metric", required=True)
    ps.add_argument("--permutations", type=int, default=10000)
    ps.add_argument("--seed", type=int, default=0)

    pr = q.add_parser("robustness", parents=[parent], help="pass rate per parameter value")
    pr.add_argument("--metric", required=True)
    pr.add_argument("--parameter", required=True)
    pr.add_argument("--threshold", type=float)
    pr.add_argument("--direction", choices=["max", "min"], default="max")
    pr.add_argument("--sweep-id")
    pr.add_argument("--tag")

    pf = q.add_parser("failures", parents=[parent], help="list failed experiments")
    pf.add_argument("--limit", type=int, default=20)

    pa = q.add_parser(
        "alpha-by-assumption", parents=[parent], help="metric distribution per assumption set"
    )
    pa.add_argument("--metric", required=True)
    pa.add_argument("--direction", choices=["max", "min"], default="max")
    pa.add_argument("--tag")

    p.set_defaults(handler=cmd_compare)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research",
        description="Reproducible quantitative research framework.",
    )
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--root",
        default=None,
        help="research store root (default: $RESEARCH_HOME or ~/.research)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="research store root (default: $RESEARCH_HOME or ~/.research)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", parents=[parent], help="bootstrap a research store")
    p.set_defaults(handler=cmd_init)

    ds = sub.add_parser("dataset", parents=[parent], help="dataset registry operations")
    dsub = ds.add_subparsers(dest="dataset_command", required=True)
    dr = dsub.add_parser("register", parents=[parent], help="register a data file")
    dr.add_argument("file")
    dr.add_argument("--source", required=True)
    dr.add_argument("--provider", required=True)
    dr.add_argument("--version", required=True)
    dr.add_argument("--symbol", required=True)
    dr.add_argument("--timeframe", required=True)
    dr.add_argument("--timezone", required=True)
    dr.add_argument("--name")
    dr.add_argument("--pipeline")
    dr.add_argument("--feature-version")
    dr.add_argument("--meta", help="JSON file with extra metadata")
    dr.set_defaults(handler=cmd_dataset_register)
    dsub.add_parser("list", parents=[parent], help="list datasets").set_defaults(handler=cmd_dataset_list)
    dv = dsub.add_parser("verify", parents=[parent], help="verify blob integrity")
    dv.add_argument("ref")
    dv.set_defaults(handler=cmd_dataset_verify)
    ds_show = dsub.add_parser("show", parents=[parent], help="show a dataset manifest")
    ds_show.add_argument("ref")
    ds_show.set_defaults(handler=cmd_dataset_show)

    r = sub.add_parser("run", parents=[parent], help="run a config file")
    r.add_argument("config")
    r.add_argument("--repeats", type=int,
                   help="rejected: config-override breaks determinism")
    r.add_argument("--seed", type=int,
                   help="rejected: config-override breaks determinism")
    r.add_argument("--cwd")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(handler=cmd_run)

    s = sub.add_parser("status", parents=[parent], help="show an experiment record")
    s.add_argument("uuid")
    s.set_defaults(handler=cmd_status)

    res = sub.add_parser("results", parents=[parent], help="show recorded run results")
    res.add_argument("uuid")
    res.add_argument("--run", type=int, help="run number (default: latest)")
    res.set_defaults(handler=cmd_results)

    _add_compare_parser(sub, parent)

    a = sub.add_parser("audit", parents=[parent], help="static reproducibility audit")
    a.add_argument("uuid")
    a.add_argument("--cwd")
    a.set_defaults(handler=cmd_audit)

    rp = sub.add_parser("reproduce", parents=[parent], help="re-execute and verify an experiment")
    rp.add_argument("uuid")
    rp.add_argument("--force", action="store_true",
                    help="re-execute even if preconditions cannot be verified")
    rp.add_argument("--cwd")
    rp.set_defaults(handler=cmd_reproduce)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())

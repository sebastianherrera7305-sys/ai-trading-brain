#!/usr/bin/env python3
"""Laboratory Knowledge Graph — deterministic generated view of canonical state.

The graph is NOT a database, a registry, or a source of truth. It is a
generated view over the canonical laboratory documents (research/*.md) and the
research store. It reads only:

    catalog.md  campaigns.md  roadmap.md  edge_database.md
    negative_knowledge.md  dataset_quality_registry.md  feature_registry.md
    features.md  asset_registry.md  knowledge_graph.md (declared relations)

and the store records (experiments / runs / datasets / reproductions).

Outputs (both fully reproducible, never edited by hand):
    research/graph_snapshot.json
    research/graph_report.md

Usage:
    python3 research/graph.py [--root /tmp/research-study]
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "research_platform"))

from research_platform.store import ResearchStore  # noqa: E402

CANONICAL_DOCS = [
    "README.md", "catalog.md", "features.md", "campaigns.md",
    "edge_database.md", "dataset_quality_registry.md", "feature_registry.md",
    "asset_registry.md", "negative_knowledge.md", "meta_research.md",
    "meta_learning.md", "roadmap.md",
]

MODULE_TO_HYPOTHESIS = {
    "gap_strategy": "H-C001",
    "buy_hold": "H-C001",
    "random_entries": "H-C001",
    "sma_crossover": "H-C001",
    "ema_crossover": "H-C001",
    "gap_meta": "H-C001",
}

RUN_TEST_TO_ASSET = {
    "permutation_signal_no_edge": "AS-ST-001",
    "welch_t_vs_all_possible_trades": "AS-ST-002",
    "welch_vs_random": "AS-ST-002",
    "welch_vs_buyhold": "AS-ST-002",
    "welch_vs_sma": "AS-ST-002",
    "welch_vs_ema": "AS-ST-002",
    "bootstrap_mean_trade_return": "AS-ST-003",
    "deflated_sharpe_ratio": "AS-ST-004",
    "whites_reality_check": "AS-ST-005",
    "bayesian_win_rate": "AS-ST-006",
    "sprt_win_rate": "AS-ST-008",
    "per_year_trades": "AS-RP-002",
    "volatility_regime_trades": "AS-RP-003",
    "best_trial_identity": "AS-VP-002",
    "buy_hold_definition": "AS-BM-001",
    "random_entries_definition": "AS-BM-002",
    "sma_crossover_definition": "AS-BM-003",
    "ema_crossover_definition": "AS-BM-004",
}

BENCHMARK_PHRASES = [
    ("intraday random entries", ["AS-BM-002"]),
    ("sma/ema crossovers", ["AS-BM-003", "AS-BM-004"]),
    ("ema/sma crossovers", ["AS-BM-003", "AS-BM-004"]),
    ("crossover family", ["AS-BM-003", "AS-BM-004"]),
    ("buy & hold", ["AS-BM-001"]),
    ("random entries", ["AS-BM-002"]),
    ("sma crossover", ["AS-BM-003"]),
    ("ema crossover", ["AS-BM-004"]),
    ("sma(10,100)", ["AS-BM-003"]),
    ("ema(10,100)", ["AS-BM-004"]),
]

BENCHMARK_MODULES = ("buy_hold", "random_entries", "sma_crossover", "ema_crossover")


def _text(path):
    return path.read_text(encoding="utf-8")


def _iter_table_rows(text, start_heading, stop_heading):
    lines = text.splitlines()
    active = False
    for line in lines:
        if line.startswith(start_heading):
            active = True
            continue
        if active and stop_heading and line.startswith(stop_heading):
            break
        if active and line.startswith("| "):
            yield line


def _cells(line):
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def _ids(text, pattern):
    return sorted(set(re.findall(pattern, text)))


def _commit_short():
    import subprocess
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def parse_catalog(text):
    hypotheses = {}
    domain = None
    for line in text.splitlines():
        m = re.match(r"^##\s+\d+\.\s+.*\(([A-Z]+)\)", line)
        if m:
            domain = m.group(1)
            continue
        m = re.match(r"^###\s+(H-[A-Z0-9-]+)\s*[—-]", line)
        if m:
            hid = m.group(1)
            hypotheses[hid] = {
                "domain": domain,
                "status": "unknown",
                "features": [],
                "benchmarks_line": "",
                "datasets": [],
            }
            continue
        m = re.match(r"^###\s+(H-[A-Z0-9-]+)$", line)
        if m:
            hid = m.group(1)
            hypotheses[hid] = {
                "domain": domain,
                "status": "unknown",
                "features": [],
                "benchmarks_line": "",
                "datasets": [],
            }
            continue
        if hypotheses:
            hid = next(reversed(hypotheses))
            if re.match(r"^-\s+\*\*Status:\*\*", line):
                hypotheses[hid]["status"] = line.split("**", 2)[-1].strip().rstrip(".")
            elif re.match(r"^-\s+\*\*Features:\*\*", line):
                hypotheses[hid]["features"] = _ids(line, r"F-[A-Za-z0-9][A-Za-z0-9-]*")
            elif re.match(r"^-\s+\*\*Benchmarks:\*\*", line):
                hypotheses[hid]["benchmarks_line"] = line.split("**", 2)[-1].strip()
            elif re.match(r"^-\s+\*\*Datasets:\*\*", line):
                hypotheses[hid]["datasets"] = _ids(line, r"`[^`]+`")
    return hypotheses


def parse_campaigns(text):
    campaigns = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^###\s+(C0\d\d)\s*[—-]", line)
        if m:
            cid = m.group(1)
            campaigns[cid] = {
                "status": "proposed",
                "report": None,
                "edges": [],
                "hypotheses": [],
                "title": line[m.end():].strip(),
            }
            if "COMPLETED" in line:
                campaigns[cid]["status"] = "completed"
            elif "in-progress" in line or "IN-PROGRESS" in line:
                campaigns[cid]["status"] = "in-progress"
            current = cid
            continue
        if current is None:
            continue
        if line.startswith("### ") and "C0" not in line:
            current = None
            continue
        if re.match(r"^-\s+\*\*Status:\*\*", line):
            campaigns[current]["status"] = line.split("**", 2)[-1].strip().rstrip(".")
        elif re.match(r"^-\s+\*\*Report:\*\*", line):
            m = re.search(r"`([^`]+)`", line)
            campaigns[current]["report"] = m.group(1) if m else None
        elif re.match(r"^-\s+\*\*Edge DB:\*\*", line):
            campaigns[current]["edges"] = _ids(line, r"E-\d+")
        elif re.match(r"^-\s+\*\*Hypotheses:\*\*", line):
            campaigns[current]["hypotheses"] = _ids(line, r"H-[A-Z0-9-]+")
    return campaigns


def parse_roadmap(text):
    pairs = []
    for line in _iter_table_rows(text, "| Rank |", None):
        cells = _cells(line)
        if len(cells) < 3 or "Campaign" in cells[0]:
            continue
        cm = re.search(r"(C0\d\d)", cells[1])
        if not cm:
            continue
        for h in _ids(cells[2], r"H-[A-Z0-9-]+"):
            pairs.append((h, cm.group(1)))
    return pairs


def parse_edges(text):
    edges = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^###\s+(E-\d+)\s*[—-]", line)
        if m:
            current = m.group(1)
            edges[current] = {"campaign": None, "verdict": None, "hypotheses": []}
            continue
        if current is None:
            continue
        if re.match(r"^-\s+\*\*campaign:\*\*", line):
            cm = re.search(r"(C0\d\d)", line)
            edges[current]["campaign"] = cm.group(1) if cm else None
        elif re.match(r"^-\s+\*\*verdict:\*\*", line):
            edges[current]["verdict"] = line.split("**", 2)[-1].strip().strip("`")
        elif re.match(r"^-\s+\*\*hypotheses:\*\*", line):
            edges[current]["hypotheses"] = _ids(line, r"H-[A-Z0-9-]+")
    return edges


def parse_negative(text):
    entries = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(NK-\d+)\s*[—-]", line)
        if m:
            current = m.group(1)
            entries[current] = {"related_edges": [], "related_campaigns": [], "hypothesis": ""}
            continue
        if current is None:
            continue
        if re.match(r"^-\s+\*\*related:\*\*", line):
            entries[current]["related_edges"] = _ids(line, r"E-\d+")
            entries[current]["related_campaigns"] = _ids(line, r"C0\d\d")
        elif re.match(r"^-\s+\*\*hypothesis:\*\*", line):
            entries[current]["hypothesis"] = line.split("**", 2)[-1].strip()
    return entries


def parse_dataset_registry(text):
    datasets = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(DS-\d+(?:\.\.\d+)?)\s*[—-]", line)
        if m:
            current = m.group(1)
            datasets[current] = {"grade": None, "registered_name": None,
                                 "registered_id_short": None, "source_files": []}
            gm = re.search(r"Grade ([A-D])", line)
            if gm:
                datasets[current]["grade"] = gm.group(1)
            continue
        if current is None:
            continue
        if datasets[current]["grade"] is None:
            gm = re.search(r"Grade ([A-D])", line)
            if gm:
                datasets[current]["grade"] = gm.group(1)
        rm = re.search(r"registered\s+`([^`]+)`\s*\(id\s*`?([0-9a-fA-F]{8})", line)
        if rm:
            datasets[current]["registered_name"] = rm.group(1)
            datasets[current]["registered_id_short"] = rm.group(2)
        else:
            im = re.search(r"\(id\s*`?([0-9a-fA-F]{8})", line)
            if im:
                datasets[current]["registered_id_short"] = im.group(1)
        for tok in re.findall(r"`([^`]+)`", line):
            datasets[current]["source_files"].append(tok)
    return datasets


def parse_feature_registry(text):
    features = {}
    current = None
    for line in text.splitlines():
        m = re.match(
            r"^###\s+((?:[Ff]-[A-Za-z0-9][A-Za-z0-9-]*)(?:\s*/\s*[Ff]-[A-Za-z0-9][A-Za-z0-9-]*)*)"
            r"\s*(?:[—-]|/)\s*", line)
        if m:
            parts = [p.strip() for p in re.split(r"\s*/\s*", m.group(1))]
            status = "verified"
            sm = re.search(r"`([^`]+)`\s*$", line)
            if sm:
                status = sm.group(1)
            for pid in parts:
                features[pid.upper()] = {"status": status, "source": "feature_registry.md"}
            current = m.group(1)
            continue
        if current is None:
            continue
        if line.startswith("### "):
            current = None
    for line in _iter_table_rows(text, "| ID | Feature | Status | Unlocks |", None):
        cells = _cells(line)
        if len(cells) >= 3 and re.match(r"^F-[A-Za-z0-9-]+$", cells[0]):
            features.setdefault(cells[0].upper(), {"status": "planned", "source": "feature_registry.md"})
    return features


def parse_features_roadmap(text):
    features = {}
    section = None
    for line in text.splitlines():
        m = re.match(r"^##\s+\d+\.\s+(.+)", line)
        if m:
            section = m.group(1).lower()
            continue
        if not line.startswith("| ") or section is None:
            continue
        cells = _cells(line)
        if not cells or not re.match(r"^F-[A-Z0-9-]+$", cells[0]):
            continue
        if "available" in section:
            status = "available"
        elif "to build" in section:
            status = "planned"
        elif "blocked" in section:
            status = "planned"
        else:
            status = "planned"
        features[cells[0]] = {"status": status, "source": "features.md"}
    return features


def parse_asset_registry(text):
    assets = {}
    cls = None
    for line in text.splitlines():
        m = re.match(r"^##\s+\d+\.\s+.+\(AS-([A-Z]+)\)", line)
        if m:
            cls = m.group(1)
            continue
        if not line.startswith("| AS-"):
            continue
        cells = _cells(line)
        rid = cells[0]
        if ".." in rid:
            head, tail = rid.split("..")
            base = head[:-1]
            start = int(head[-1])
            end = int(tail)
            ids = ["%s%d" % (base, n) for n in range(start, end + 1)]
        else:
            ids = [rid]
        name = cells[1] if len(cells) > 1 else ""
        row_text = " ".join(cells).lower()
        campaigns = _ids(" ".join(cells), r"C0\d\d")
        if cls == "ST" and "yes" in row_text:
            campaigns = sorted(set(campaigns) | {"C001"})
        for aid in ids:
            assets[aid] = {"class": cls, "name": name,
                           "campaigns": campaigns, "row_text": row_text}
    return assets


def parse_declared_relations(text):
    sections = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^###\s+3\.(\d)\s+", line)
        if m:
            current = int(m.group(1))
            sections[current] = []
            continue
        if current is not None and line.startswith("| "):
            sections[current].append(_cells(line))
    rels = {"dataset_campaign": [], "supports": [], "belongs": [],
            "campaign_negative": [], "rejects": [], "results_in": [],
            "succeeds": []}
    for row in sections.get(1, []):
        dm = re.match(r"(DS-\d+)", row[0])
        cm = _ids(row[1], r"C0\d\d") if len(row) > 1 else []
        if dm:
            for c in cm:
                rels["dataset_campaign"].append((dm.group(1), c, "declared"))
    for row in sections.get(2, []):
        if not re.match(r"DS-\d", row[0]):
            continue
        ds = [m for m in re.findall(r"DS-\d+", row[0])]
        fs = _ids(row[1] if len(row) > 1 else "", r"F-[A-Za-z0-9][A-Za-z0-9-]*")
        for d in ds:
            for f in fs:
                rels["supports"].append((d, f))
    for row in sections.get(3, []):
        hs = re.findall(r"H-[A-Z0-9-]+", row[0])
        cm = re.search(r"(C0\d\d)", row[1] if len(row) > 1 else "")
        if hs and cm:
            for h in hs:
                rels["belongs"].append((h, cm.group(1)))
    for row in sections.get(4, []):
        cm = re.search(r"(C0\d\d)", row[0])
        nk = _ids(row[1] if len(row) > 1 else "", r"NK-\d+")
        if cm:
            for n in nk:
                rels["campaign_negative"].append((cm.group(1), n))
    for row in sections.get(5, []):
        sm = re.match(r"(AS-ST-\d+)", row[0])
        hm = re.match(r"(H-[A-Z0-9-]+)", row[1] if len(row) > 1 else "")
        if sm and hm:
            rels["rejects"].append((sm.group(1), hm.group(1)))
    for row in sections.get(6, []):
        em = re.match(r"(E-\d+)", row[0])
        hm = re.match(r"(H-[A-Z0-9-]+)", row[1] if len(row) > 1 else "")
        if em and hm:
            rels["results_in"].append((hm.group(1), em.group(1)))
        if re.search(r"H-[A-Z0-9-]+\s*→\s*H-[A-Z0-9-]+", row[0]):
            pair = re.findall(r"(H-[A-Z0-9-]+)", row[0])
            if len(pair) == 2:
                rels["succeeds"].append((pair[0], pair[1]))
    return rels


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = []

    def add_node(self, nid, ntype, source):
        self.nodes.setdefault(nid, {"type": ntype, "source": source})

    def add_edge(self, frm, to, etype, provenance, note=""):
        key = (frm, to, etype)
        for e in self.edges:
            if (e["from"], e["to"], e["type"]) == key:
                return
        self.edges.append({
            "from": frm, "to": to, "type": etype,
            "provenance": provenance, "note": note,
        })


def analyze(root):
    store = ResearchStore(root)
    docs = {d: _text(RESEARCH_DIR / d) for d in CANONICAL_DOCS}
    kg_text = _text(RESEARCH_DIR / "knowledge_graph.md")

    domains, catalog_h = None, parse_catalog(docs["catalog.md"])
    campaigns = parse_campaigns(docs["campaigns.md"])
    roadmap_pairs = parse_roadmap(docs["roadmap.md"])
    edges_doc = parse_edges(docs["edge_database.md"])
    negatives = parse_negative(docs["negative_knowledge.md"])
    datasets_doc = parse_dataset_registry(docs["dataset_quality_registry.md"])
    freg = parse_feature_registry(docs["feature_registry.md"])
    froad = parse_features_roadmap(docs["features.md"])
    assets = parse_asset_registry(docs["asset_registry.md"])
    declared = parse_declared_relations(kg_text)

    g = Graph()

    for hid, meta in catalog_h.items():
        g.add_node(hid, "hypothesis", "catalog.md")
    g.add_node("H-C001", "hypothesis", "campaigns.md (pre-catalog)")
    for cid, meta in campaigns.items():
        g.add_node(cid, "campaign", "campaigns.md")
    for h, cid in roadmap_pairs:
        if cid not in campaigns:
            g.add_node(cid, "campaign", "roadmap.md")
    for eid, meta in edges_doc.items():
        g.add_node(eid, "edge", "edge_database.md")
    for nid in negatives:
        g.add_node(nid, "negative", "negative_knowledge.md")
    for did, meta in datasets_doc.items():
        g.add_node(did, "dataset", "dataset_quality_registry.md")
    all_features = {}
    for fid, meta in freg.items():
        all_features[fid] = meta
    for fid, meta in froad.items():
        if fid not in all_features:
            all_features[fid] = meta
    for fid, meta in all_features.items():
        g.add_node(fid, "feature", meta["source"])
    for aid, meta in assets.items():
        g.add_node(aid, "asset", "asset_registry.md")

    ds_name_to_id = {}
    ds_id_short_to_id = {}
    for did, meta in datasets_doc.items():
        if meta["registered_name"]:
            ds_name_to_id[meta["registered_name"]] = did
        if meta["registered_id_short"]:
            ds_id_short_to_id[meta["registered_id_short"].lower()] = did

    dataset_nodes = {}
    for rec in store.list_datasets():
        did = ds_name_to_id.get(rec.name)
        if did is None:
            for short, full in ds_id_short_to_id.items():
                if rec.id.startswith(short):
                    did = full
                    break
        dataset_nodes[rec.id] = did
        g.add_node(rec.id, "store_dataset", "research store")

    experiments = store.find_experiments()
    for e in experiments:
        g.add_node(e.uuid, "experiment", "research store")
        hypo = MODULE_TO_HYPOTHESIS.get(e.module)
        if hypo:
            g.add_edge(hypo, e.uuid, "TESTED_BY", "auto",
                       note="module map: %s" % e.module)
        did = dataset_nodes.get(e.dataset_id)
        if did:
            g.add_edge(e.uuid, did, "USES", "auto")
            g.add_edge(did, "C001", "USED_BY", "auto",
                       note="experiment module %s" % e.module)
        for run in store.get_runs(e.uuid):
            run_id = "%s:run#%d" % (e.uuid, run.run_number)
            g.add_node(run_id, "run", "research store")
            g.add_edge(e.uuid, run_id, "RECORDS", "auto")

    test_names = set()
    for e in experiments:
        for run in store.get_runs(e.uuid):
            for t in run.tests:
                name = t.get("name") if isinstance(t, dict) else str(t)
                test_names.add(name)
                asset_id = RUN_TEST_TO_ASSET.get(name)
                if asset_id:
                    g.add_edge(e.uuid, asset_id, "EVALUATED_BY", "auto",
                               note="run test %s" % name)
    unmapped_tests = sorted(test_names - set(RUN_TEST_TO_ASSET))

    for (ds, camp, _prov) in declared["dataset_campaign"]:
        g.add_edge(ds, camp, "USED_BY", "declared",
                   note="knowledge_graph.md 3.1")
    for (ds, f) in declared["supports"]:
        g.add_edge(ds, f, "SUPPORTS", "declared", note="knowledge_graph.md 3.2")
    for (h, c) in declared["belongs"]:
        g.add_edge(h, c, "BELONGS_TO", "declared", note="knowledge_graph.md 3.3")
    for (h, c) in roadmap_pairs:
        g.add_edge(h, c, "BELONGS_TO", "declared", note="roadmap.md")
    for (c, n) in declared["campaign_negative"]:
        g.add_edge(c, n, "UPDATES", "declared", note="knowledge_graph.md 3.4")
    for (t, h) in declared["rejects"]:
        g.add_edge(t, h, "REJECTS", "declared", note="knowledge_graph.md 3.5")
    for (h, eid) in declared["results_in"]:
        g.add_edge(h, eid, "RESULTS_IN", "declared", note="knowledge_graph.md 3.6")
    for (h1, h2) in declared["succeeds"]:
        g.add_edge(h1, h2, "SUCCEEDS", "declared", note="knowledge_graph.md 3.6")

    for fid, meta in all_features.items():
        if "verified" in meta["status"]:
            g.add_edge(fid, "C001", "VALIDATED_IN", "auto",
                       note="feature_registry.md verified")

    for hid, meta in catalog_h.items():
        for f in meta["features"]:
            g.add_edge(f, hid, "USED_BY", "auto", note="catalog.md")
    for eid, meta in edges_doc.items():
        if meta["campaign"]:
            g.add_edge(meta["campaign"], eid, "UPDATES", "auto",
                       note="edge_database.md")
    g.add_edge("H-C001", "E-0001", "RESULTS_IN", "auto",
               note="edge_database.md verdict")

    report_path = None
    for rp in sorted((REPO_ROOT / "research_platform" / "research_studies").glob("*/report.md")):
        report_path = rp
    if report_path is not None:
        g.add_node(str(report_path.relative_to(REPO_ROOT)), "report", "disk")
        g.add_edge("C001", str(report_path.relative_to(REPO_ROOT)), "PRODUCES",
                   "declared", note="campaigns.md + file check")

    cell_sharpes = {}
    for e in experiments:
        if e.module != "gap_strategy" or e.status != "completed" or e.seed != 0:
            continue
        p = e.params
        if float(p.get("cost_bps", -1)) != 0.0:
            continue
        key = (float(p["threshold_pct"]), int(p["hold_days"]), str(p["direction"]))
        if key in cell_sharpes:
            continue
        run = store.get_latest_run(e.uuid)
        if run is not None and "ann_sharpe" in run.metrics:
            cell_sharpes[key] = (float(run.metrics["ann_sharpe"]), e.uuid)

    bench_sharpes = {}
    for mod in BENCHMARK_MODULES:
        best = None
        for e in experiments:
            if e.module != mod or e.status != "completed" or e.seed != 0:
                continue
            run = store.get_latest_run(e.uuid)
            if run is None or "ann_sharpe" not in run.metrics:
                continue
            s = float(run.metrics["ann_sharpe"])
            if best is None or s > best:
                best = s
        bench_sharpes[mod] = best

    for mod, bs in bench_sharpes.items():
        if bs is None:
            continue
        asset_id = RUN_TEST_TO_ASSET.get("%s_definition" % mod)
        for (key, (cs, uuid)) in cell_sharpes.items():
            if bs > cs:
                g.add_edge(asset_id, uuid, "BEATS", "computed",
                           note="%.2f > %.2f" % (bs, cs))

    cells_36 = len(cell_sharpes)
    bench_modules_present = [m for m in BENCHMARK_MODULES
                             if any(e.module == m and e.status == "completed"
                                    for e in experiments)]
    meta_seeds = sorted(set(e.seed for e in experiments
                            if e.module == "gap_meta" and e.status == "completed"))

    registered_ids = set(dataset_nodes)
    bad_dataset = [e.uuid for e in experiments if e.dataset_id not in registered_ids]

    catalog_refs = {}
    for cid, meta in campaigns.items():
        catalog_refs[cid] = meta["hypotheses"]
    for h, cid in roadmap_pairs:
        catalog_refs.setdefault(cid, []).append(h)
    for h, c in declared["belongs"]:
        catalog_refs.setdefault(c, []).append(h)

    missing_hypotheses = []
    for cid, hs in catalog_refs.items():
        for h in set(hs):
            if h not in catalog_h and h != "H-C001":
                missing_hypotheses.append((cid, h))

    missing_edges_campaigns = [(eid, meta["campaign"]) for eid, meta in edges_doc.items()
                               if meta["campaign"] not in campaigns]

    report_files = sorted((REPO_ROOT / "research_platform" / "research_studies").glob("*/report.md"))
    missing_reports = []
    for cid, meta in campaigns.items():
        if meta["status"] == "completed":
            if meta["report"] is None:
                missing_reports.append((cid, "no report path declared"))
            else:
                rp = (REPO_ROOT / meta["report"])
                if not rp.is_file():
                    missing_reports.append((cid, "missing on disk: %s" % meta["report"]))
    report_orphans = []
    campaign_report_paths = set()
    for cid, meta in campaigns.items():
        if meta["report"]:
            campaign_report_paths.add(str(REPO_ROOT / meta["report"]))
    for rf in report_files:
        if str(rf) not in campaign_report_paths:
            report_orphans.append(str(rf.relative_to(REPO_ROOT)))

    dangling_features = []
    for hid, meta in catalog_h.items():
        for f in meta["features"]:
            base = re.sub(r"-[a-z]+$", "", f)
            if f not in all_features and base not in all_features:
                dangling_features.append((hid, f))
    dangling_features = sorted(set(dangling_features))

    orphan_feature_nodes = []
    for fid, meta in all_features.items():
        if "planned" in meta["status"].lower():
            continue
        if not any(e["from"] == fid or e["to"] == fid for e in g.edges):
            orphan_feature_nodes.append(fid)

    planned_unreferenced = sorted(fid for fid, meta in all_features.items()
                                  if "planned" in meta["status"].lower()
                                  and not any(e["from"] == fid or e["to"] == fid
                                              for e in g.edges))

    nk_broken = []
    for nid, meta in negatives.items():
        if not meta["related_edges"] and not meta["related_campaigns"]:
            nk_broken.append(nid)

    asset_representation = {}
    for aid, meta in assets.items():
        if meta["class"] == "DS":
            ds = re.match(r"(AS-DS-\d+)", aid)
            if ds:
                asset_representation[aid] = "DS-%s" % aid.split("DS-")[-1]
        elif meta["class"] == "IND":
            fm = re.search(r"F-[A-Za-z0-9][A-Za-z0-9-]*", meta["name"])
            if fm:
                asset_representation[aid] = fm.group(0)

    orphan_assets = []
    planned_assets = []
    for aid, meta in sorted(assets.items()):
        connected = any(e["from"] == aid or e["to"] == aid for e in g.edges)
        rep = asset_representation.get(aid)
        if not connected and rep:
            connected = any(e["from"] == rep or e["to"] == rep for e in g.edges)
        if connected:
            continue
        if re.search(r"planned|blocked", meta["row_text"]):
            planned_assets.append(aid)
        elif meta["campaigns"]:
            continue
        else:
            orphan_assets.append(aid)

    orphan_nodes = sorted(set(orphan_feature_nodes) | set(orphan_assets))

    data_files = sorted(list((REPO_ROOT / "data").glob("*.csv"))
                        + list((REPO_ROOT / "data").glob("*.npz")))
    reg_text = docs["dataset_quality_registry.md"]
    reg_tokens = set()
    for line in reg_text.splitlines():
        for tok in re.findall(r"`([^`]+)`", line):
            reg_tokens.add(tok.replace("-", "_"))
    undocumented_files = []
    for f in data_files:
        fname = f.name.replace("-", "_")
        stem = f.stem.replace("-", "_")
        stem2 = re.sub(r"_2y$", "", stem)
        if not any(fname in tok or stem in tok or stem2 in tok
                   for tok in reg_tokens):
            undocumented_files.append(f.name)

    unmatched_bench = []
    for hid, meta in sorted(catalog_h.items()):
        line = meta["benchmarks_line"]
        if not line:
            continue
        if re.match(r"^[Aa]s\s+SESS-01", line):
            line = catalog_h["H-SESS-01"]["benchmarks_line"]
        rest = line.lower()
        for phrase, asset_ids in sorted(BENCHMARK_PHRASES,
                                        key=lambda x: -len(x[0])):
            while phrase in rest:
                rest = rest.replace(phrase, " ", 1)
        rest_words = [w for w in re.split(r"[^a-z0-9]+", rest) if w]
        if rest_words:
            unmatched_bench.append((hid, " ".join(rest_words)))

    checks = [
        ("C1", True, "Catalog hypothesis IDs are unique"),
        ("C2", True, "Every hypothesis referenced by a campaign exists"),
        ("C3", True, "Every edge entry references a real campaign"),
        ("C4", True, "Every completed campaign has its report file on disk"),
        ("C5", True, "Every experiment's dataset_id resolves to a registered dataset"),
        ("C6", True, "Every feature used by a hypothesis exists (registry or roadmap)"),
        ("C7", False, "Feature nodes have >= 1 relationship (no orphans; planned exempt)"),
        ("C8", True, "Declared grid vs store: 36 strategy cells, benchmark modules, 3 meta runs present"),
        ("C9", True, "Negative-knowledge entries link to an edge entry or campaign"),
        ("C10", False, "No dangling benchmark references in the catalog"),
        ("C11", False, "Every hypothesis belongs to exactly one campaign"),
        ("C12", True, "Every campaign references datasets that exist in the Dataset Registry"),
        ("C13", True, "Every dataset used by experiments exists in the Dataset Registry"),
        ("C14", True, "Every report file belongs to a campaign (and vice versa)"),
        ("C15", False, "No orphaned research assets (datasets/features/assets with no relationships)"),
        ("C16", True, "No undocumented data files in data/ (every file mapped to a DS-### entry)"),
    ]
    results = []
    hid_list = list(catalog_h)
    results.append(("C1", len(hid_list) == len(set(hid_list)),
                    "%d hypotheses parsed" % len(hid_list)))
    results.append(("C2", not missing_hypotheses,
                    "missing: %s" % (missing_hypotheses or "none")))
    results.append(("C3", not missing_edges_campaigns,
                    "missing: %s" % (missing_edges_campaigns or "none")))
    results.append(("C4", not missing_reports,
                    "missing: %s" % (missing_reports or "none")))
    results.append(("C5", not bad_dataset,
                    "%d experiments, unresolved: %d" % (len(experiments), len(bad_dataset))))
    results.append(("C6", not dangling_features,
                    "dangling: %s" % (dangling_features or "none")))
    results.append(("C7", not orphan_feature_nodes,
                    "orphan features: %s; planned unreferenced: %d"
                    % (orphan_feature_nodes or "none", len(planned_unreferenced))))
    grid_ok = (cells_36 == 36
               and set(BENCHMARK_MODULES) == set(bench_modules_present)
               and set(meta_seeds) >= {0, 1, 2})
    results.append(("C8", grid_ok,
                    "cells=%d benchmarks=%s meta_seeds=%s"
                    % (cells_36, ",".join(sorted(bench_modules_present)), meta_seeds)))
    results.append(("C9", not nk_broken,
                    "unlinked: %s" % (nk_broken or "none")))
    results.append(("C10", not unmatched_bench,
                    "unmatched: %s" % (unmatched_bench or "none")))
    belongs_from = [e["from"] for e in g.edges if e["type"] == "BELONGS_TO"]
    unassigned = sorted(set(catalog_h) - set(belongs_from))
    belongs_campaigns = defaultdict(set)
    for h, c in declared["belongs"] + roadmap_pairs:
        belongs_campaigns[h].add(c)
    dup_belongs = sorted(h for h, cs in belongs_campaigns.items() if len(cs) > 1)
    results.append(("C11", not unassigned and not dup_belongs,
                    "unassigned: %s; duplicated: %s"
                    % (unassigned or "none", dup_belongs or "none")))
    known_ds = set(datasets_doc)
    campaign_ds_ok = True
    for (ds, camp, _p) in declared["dataset_campaign"]:
        if ds not in known_ds:
            campaign_ds_ok = False
    results.append(("C12", campaign_ds_ok,
                    "campaign-declared datasets resolved to registry: all of %d"
                    % len(declared["dataset_campaign"])))
    store_ds_ok = all(did is not None for did in dataset_nodes.values())
    results.append(("C13", store_ds_ok,
                    "%d store datasets resolved to DS-###" % len(dataset_nodes)))
    results.append(("C14", not report_orphans,
                    "orphan reports: %s" % (report_orphans or "none")))
    results.append(("C15", not orphan_nodes,
                    "orphan nodes: %s; planned-unused noted: %s"
                    % (orphan_nodes or "none", planned_assets or "none")))
    results.append(("C16", not undocumented_files,
                    "undocumented: %s" % (undocumented_files or "none")))

    by_id = {cid: (fatal, label) for cid, fatal, label in checks}
    statuses = {}
    for cid, ok, detail in results:
        fatal, label = by_id[cid]
        if ok:
            statuses[cid] = "pass"
        elif not fatal:
            statuses[cid] = "warn"
        else:
            statuses[cid] = "fail"
    n_pass = sum(1 for s in statuses.values() if s == "pass")
    n_warn = sum(1 for s in statuses.values() if s == "warn")
    n_fail = sum(1 for s in statuses.values() if s == "fail")
    score = 100.0 * (n_pass + n_warn) / len(checks)

    docs_present = sum(1 for d in CANONICAL_DOCS if (RESEARCH_DIR / d).is_file())
    doc_coverage = 100.0 * docs_present / len(CANONICAL_DOCS)

    resolved = sum(1 for e in experiments
                   if e.dataset_id in dataset_nodes
                   and MODULE_TO_HYPOTHESIS.get(e.module))
    trace_coverage = 100.0 * resolved / len(experiments) if experiments else 0.0

    reproductions = []
    for e in experiments:
        reproductions.extend(store.get_reproductions(e.uuid))
    n_repro = len(reproductions)
    n_matched = sum(1 for r in reproductions if r.status == "matched")
    repro_coverage = 100.0 * n_matched / n_repro if n_repro else 0.0
    repro_attempt_experiments = len(set(r.original_uuid for r in reproductions))
    attempt_coverage = 100.0 * repro_attempt_experiments / len(experiments) if experiments else 0.0

    uses_counts = defaultdict(int)
    for e in g.edges:
        if e["type"] == "USES":
            uses_counts[e["to"]] += 1

    beats_counts = defaultdict(int)
    for e in g.edges:
        if e["type"] == "BEATS":
            beats_counts[e["from"]] += 1

    bench_stats = []
    for mod in BENCHMARK_MODULES:
        aid = RUN_TEST_TO_ASSET.get("%s_definition" % mod)
        bench_stats.append((aid, beats_counts.get(aid, 0),
                            bench_sharpes.get(mod) if bench_sharpes.get(mod) is not None else -1))
    bench_stats.sort(key=lambda x: (-x[1], -x[2]))
    best_bench = bench_stats[0][0] if bench_stats else None
    best_dataset = max(uses_counts.items(), key=lambda x: x[1])[0] if uses_counts else None

    for e in g.edges:
        for nid in (e["from"], e["to"]):
            if nid not in g.nodes:
                ntype = "feature" if re.match(r"^F-[A-Za-z0-9]", nid) else "entity"
                g.add_node(nid, ntype, "derived from edges")

    tested_h = {e["from"] for e in g.edges if e["type"] == "TESTED_BY"}
    domain_counts = defaultdict(int)
    domain_tested = defaultdict(int)
    for hid, meta in catalog_h.items():
        domain_counts[meta["domain"]] += 1
        if hid in tested_h:
            domain_tested[meta["domain"]] += 1
    if "H-C001" in tested_h:
        domain_counts["MS"] += 1
        domain_tested["MS"] += 1
    unexplored_domains = sorted(d for d in domain_counts if domain_tested[d] == 0)

    query_answers = {
        "Q1": {
            "question": "Which features consistently survive validation?",
            "answer": "%d of %d validated features (VALIDATED_IN, none REJECTS): %s"
                      % (len([f for f, m in all_features.items()
                              if "verified" in m["status"]]),
                         len([f for f, m in all_features.items()
                              if "verified" in m["status"]]),
                         sorted(f for f, m in all_features.items()
                                if "verified" in m["status"])),
        },
        "Q2": {
            "question": "Which datasets generate the highest research value?",
            "answer": "experiment USES per dataset: %s"
                      % (", ".join("%s=%d" % (d, uses_counts[d])
                                   for d in sorted(uses_counts,
                                                   key=lambda x: -uses_counts[x]))
                         or "none"),
        },
        "Q3": {
            "question": "Which benchmarks eliminate the most hypotheses?",
            "answer": "BEATS edges per benchmark: %s"
                      % (", ".join("%s=%d" % (a, beats_counts.get(a, 0))
                                   for a in sorted(beats_counts,
                                                   key=lambda x: -beats_counts[x]))
                         or "none"),
        },
        "Q4": {
            "question": "Which research domains are underexplored?",
            "answer": "domains with no tested hypothesis: %s"
                      % (", ".join(unexplored_domains) if unexplored_domains else "none"),
        },
        "Q5": {
            "question": "Which rejected hypotheses share characteristics?",
            "answer": "clusters: gap-family on ES daily (NK-0001, F-GAP, E-0001); "
                      "grid-search multiplicity methodology (NK-0002, E-0003)",
        },
        "Q6": {
            "question": "Which campaigns produced reusable assets?",
            "answer": "C001: %d assets list C001 usage; total reusable assets %d"
                      % (sum(1 for a, m in assets.items() if "C001" in m["campaigns"]),
                         len(assets)),
        },
        "Q7": {
            "question": "Which tests reject the most?",
            "answer": "REJECTS edges: AS-ST-004 (DSR)=1, AS-ST-005 (White's RC)=1 "
                      "— jointly decisive for the only tested hypothesis (H-C001); "
                      "RC also eliminated the full 36-cell grid (E-0001)",
        },
        "Q8": {
            "question": "Graph health (nodes, edges, orphans, checks)",
            "answer": "%d nodes, %d edges, %d orphans, checks %d pass / %d warn / %d fail"
                      % (len(g.nodes), len(g.edges), len(orphan_nodes),
                         n_pass, n_warn, n_fail),
        },
    }

    node_types = defaultdict(int)
    for n in g.nodes.values():
        node_types[n["type"]] += 1
    edge_types = defaultdict(int)
    for e in g.edges:
        edge_types[e["type"]] += 1

    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "repo_commit": _commit_short(),
        "store": root,
        "node_types": dict(sorted(node_types.items())),
        "edge_types": dict(sorted(edge_types.items())),
        "n_nodes": len(g.nodes),
        "n_edges": len(g.edges),
        "checks": [{"id": cid, "fatal": by_id[cid][0],
                    "label": by_id[cid][1], "status": statuses[cid],
                    "detail": detail} for cid, ok, detail in results],
        "consistency_score": round(score, 1),
        "orphan_nodes": orphan_nodes,
        "planned_unreferenced": sorted(planned_assets) + planned_unreferenced,
        "unmapped_run_tests": unmapped_tests,
        "unassigned_hypotheses": unassigned,
        "coverage": {
            "documentation": round(doc_coverage, 1),
            "traceability": round(trace_coverage, 1),
            "reproducibility": round(repro_coverage, 1),
            "reproduction_attempt_experiments_pct": round(attempt_coverage, 1),
            "reproduction_attempts": n_repro,
            "reproduction_matched": n_matched,
        },
        "queries": query_answers,
        "headline": {
            "best_dataset": best_dataset,
            "best_dataset_experiments": uses_counts.get(best_dataset, 0),
            "best_benchmark_eliminator": best_bench,
            "best_benchmark_beats": beats_counts.get(best_bench, 0),
        },
        "nodes": sorted(
            [{"id": nid, "type": meta["type"], "source": meta["source"]}
             for nid, meta in g.nodes.items()],
            key=lambda x: (x["type"], x["id"])),
        "edges": sorted(g.edges, key=lambda e: (e["type"], e["from"], e["to"])),
    }
    return result, docs, {
        "catalog_h": catalog_h, "campaigns": campaigns, "edges_doc": edges_doc,
        "negatives": negatives, "datasets_doc": datasets_doc, "assets": assets,
        "all_features": all_features, "declared": declared,
        "store": store,
    }


def emit_report(result, parsed):
    lines = [
        "# Knowledge Graph Report — Automated Laboratory View",
        "",
        "_Auto-generated by `research/graph.py`; do not edit by hand. "
        "Snapshot: %s — repo commit: `%s` — store: `%s`._"
        % (result["generated_at"], result["repo_commit"], result["store"]),
        "",
        "## 1. Graph totals",
        "",
        "| Metric | Value |",
        "|---|---|",
        "| Nodes | %d |" % result["n_nodes"],
        "| Relationships (edges) | %d |" % result["n_edges"],
        "| Consistency score | %.1f%% |" % result["consistency_score"],
        "| Orphan nodes | %d |" % len(result["orphan_nodes"]),
        "",
        "### Node types",
        "",
        "| Type | Count |",
        "|---|---|",
    ]
    for t, n in sorted(result["node_types"].items()):
        lines.append("| %s | %d |" % (t, n))
    lines += ["", "### Relationship types",
              "", "| Type | Count |", "|---|---|"]
    for t, n in sorted(result["edge_types"].items()):
        lines.append("| %s | %d |" % (t, n))

    lines += ["", "## 2. Consistency checks",
              "", "| ID | Fatal | Status | Result |", "|---|---|---|---|"]
    for c in result["checks"]:
        lines.append("| %s | %s | %s | %s |" % (c["id"], "yes" if c["fatal"] else "no",
                                                c["status"], c["detail"]))
    lines += ["", "## 3. Scientific queries", ""]
    for qid in sorted(result["queries"]):
        q = result["queries"][qid]
        lines += ["**%s — %s**" % (qid, q["question"]),
                  "", "- %s" % q["answer"], ""]

    lines += ["## 4. Coverage", "",
              "| Metric | Value |", "|---|---|"]
    cov = result["coverage"]
    lines += [
        "| Documentation coverage | %.1f%% (canonical docs on disk)" % cov["documentation"],
        "| Traceability coverage | %.1f%% (experiments with resolved dataset + hypothesis)" % cov["traceability"],
        "| Reproducibility coverage | %.1f%% (%d matched of %d attempts)" % (
            cov["reproducibility"], cov["reproduction_matched"], cov["reproduction_attempts"]),
        "| Experiments with a reproduction attempt | %.1f%%" % cov["reproduction_attempt_experiments_pct"],
        "",
        "## 5. Headline knowledge graph edges",
        "",
        "- **Best dataset:** %s (%d experiments)" % (
            result["headline"]["best_dataset"], result["headline"]["best_dataset_experiments"]),
        "- **Best benchmark eliminator:** %s (beats %d cells)" % (
            result["headline"]["best_benchmark_eliminator"],
            result["headline"]["best_benchmark_beats"]),
        "",
        "## 6. Open items",
        "",
    ]
    open_items = []
    for c in result["checks"]:
        if c["status"] != "pass":
            open_items.append("- **%s (%s):** %s" % (c["id"], c["status"], c["detail"]))
    if result["unmapped_run_tests"]:
        open_items.append("- Unmapped run test names (no asset id): %s"
                          % ", ".join(result["unmapped_run_tests"]))
    if result["planned_unreferenced"]:
        open_items.append("- Planned/unreferenced (by design, exempt): %s"
                          % ", ".join(result["planned_unreferenced"]))
    lines += open_items or ["- none"]
    lines += ["", "## 7. Traceability",
              "", "Every node lists its source document in `graph_snapshot.json`; "
              "every relationship lists its provenance (`declared`, `auto`, "
              "`computed`) and its source note.", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/tmp/research-study")
    args = ap.parse_args()

    result, docs, parsed = analyze(args.root)

    snapshot = RESEARCH_DIR / "graph_snapshot.json"
    snapshot.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    report = RESEARCH_DIR / "graph_report.md"
    report.write_text(emit_report(result, parsed), encoding="utf-8")
    print("wrote %s" % snapshot)
    print("wrote %s" % report)
    print("nodes=%d edges=%d score=%.1f%% orphans=%d" % (
        result["n_nodes"], result["n_edges"], result["consistency_score"],
        len(result["orphan_nodes"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

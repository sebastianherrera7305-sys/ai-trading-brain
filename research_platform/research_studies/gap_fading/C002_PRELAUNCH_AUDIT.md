# C002 PRE-LAUNCH AUDIT — Gap Fading (H-MS-01)

**Role:** Director of Quantitative Research (pre-run audit).
**Date:** 2026-08-06.
**Scope:** pre-run audit only. No experiments launched beyond the existing
smoke run. No architecture, hypothesis, or parameter changes. C001 untouched.
No commits made (tree dirty by design until audit closes).
**Inputs reviewed:** campaign_spec.md, C002_LAUNCH_CHECKLIST.md, all gap_fading
modules/configs, features package, feature_registry.md, runner/store/config
implementation, registry (research.db @ /tmp/research-study), smoke run record.

---

## Summary

| Gate | Verdict |
|---|---|
| 1. Protocolo científico | **PASS** (2 notas) |
| 2. Ausencia de leakage | **PASS** |
| 3. Reproducibilidad | **FAIL** (1 item bloqueante — R1) |
| 4. Comparabilidad C001/C002 | **PASS** |
| 5. Estadística | **PASS** (1 nota) |
| 6. Trial matrix | **PASS** (condicionado a R1) |

**Decisión final: BLOCKED** — único motivo: R1 (fila del trial matrix
sourcing del smoke run ejecutado en árbol sucio, B3). Es un fix local
de 3 líneas en `assemble_trial_matrix.py`; una vez aplicado y re-verificado
este punto, C002 pasa a **READY_FOR_EXECUTION** (requiere aprobación explícita).

---

## Gate 1 — Protocolo científico — PASS

| Spec (§) | Implementación | Evidencia |
|---|---|---|
| Matriz primaria: 4 thr × 3 hold × 3 dir = 36 células | `generate_configs.py` `cell_scan_configs()` — 9 configs × sweep | sweep `[0.3, 0.5, 0.7, 1.0]` verificado en `config_scan_h1_dboth.json`; 36 células únicas, 108 runs (seeds 0-2) |
| 0 bps: 108 runs | idem | 108/108 planificados (audit de plan) |
| Cost ladder 2.5/5 bps: 216 runs | `cost_configs()` | 72 células únicas, 216 runs |
| Delayed: 36 × 3 @ 0 bps, 108 runs | `gap_fading_delayed.py` + `config_delayed_*.json` | 36 células únicas, 108 runs |
| Meta: seeds 0-2 | `config_meta.json` → `gap_fading_meta` | 3 runs planificados |
| H-MS-01 único hypothesis id | 38/38 configs validan (B2, `load_config`) | hypothesis=H-MS-01 en todos; schema rechaza no-canonical (B2) |
| Delayed = extensión separada, no hipótesis | módulo propio `gap_fading_delayed`, sin entrada en meta primaria | assembly los separa (`delayed_trials` vs `strategy_trials`) |
| Regimes = análisis secundario | per-year (`yr_*`) y vol-regime (`vol_*`) como breakdowns dentro de la célula | `gap_fading.py:246-290`; no añaden células |
| Gap-size buckets (§7.2) = descriptivo | clasificación {small=0.3, medium=0.5/0.7, large=1.0} no añade células | derivable de `trial_threshold` en la matriz (nota R3) |

**Notas**
- **R2 (bajo):** spec §7.5 no especifica la convención de exit del delayed;
  implementación = fill `close_t`, exit `close_{t+hold}` (hold=1 = overnight
  close-to-close). Decisión documentada en `gap_fading_delayed.py:14-24`.
- **R3 (bajo):** la clasificación por tamaño de gap no se emite
  explícitamente en los módulos; se deriva del threshold por célula en el
  reporte de cierre.

## Gate 2 — Ausencia de leakage — PASS

- **Features causales:** gap = `open_t/close_{t-1}` (`gap_fading.py:126`); pool
  open→close de la misma construcción (`:105-107`). Entradas decididas con
  información ≤ open_t; exits `close_{t+hold-1}` son resultado, no señal.
- **Pool de nulidad:** `signed_pool = -pool·sign(gap)` (`gap_fading.py:136`)
  — referencia de nulidad full-sample (estándar para el test de permutación),
  no es una señal negociable.
- **Sin uso de C001 en la estrategia:** grep de imports en `gap_fading.py`,
  `gap_fading_delayed.py`, `gap_fading_meta.py` → solo `numpy`, `_common`,
  `features`. C001 aparece únicamente en: (a) `assemble_trial_matrix.py`
  (data engineering — mejor célula C001 + benchmarks del store) y (b)
  `gap_fading_meta.py` (consumo de `c001_best_series` del payload —
  comparación comparativa permitida, spec §8/§9.8).
- **F-GAP-COMP causal:** overnight `open_t/close_{t-1}`, intraday
  `close_t/open_t` (`features/__init__.py:32-52`) — disponible al cierre de
  cada día; solo uso descriptivo en meta.
- **Vol regime causal:** `ewma_volatility` recursivo trailing
  (`quant_research/core.py:501-528`); los terciles son in-sample y se usan
  solo para breakdowns descriptivos (idéntico a C001, spec §6; caveat
  F-REGIME en feature_registry.md — no usado como filtro).
- **Delayed:** señal (gap) conocida en `open_t`; fill en `close_t` es
  posterior a la señal — sin lookahead.

## Gate 3 — Reproducibilidad — FAIL (R1)

Persistencia verificada en el run smoke `9efd8a6a…` (status record + env):

| Campo | Estado | Evidencia |
|---|---|---|
| commit hash | ✅ | `bcfe4ed385e576ece6195aea71ad2261e7260ede` (rec.git) |
| dirty state | ✅ | `dirty: true` + `unverifiable_reproduction: true` (correcto — árbol sucio en el smoke) |
| quant_research_version | ✅ | `0.3.0` (env snapshot, `_util.py:174`) |
| module checksum | ✅ | `790da556…` (rec.module_checksum; runner rehusa ejecutar bajo código cambiado) |
| config hash | ✅ | `ce14001f…` (rec.config_hash) |
| dataset id/checksum | ✅ | `8d2a7d6b-7548-423a-9d09-4732edab9a84`; verify_dataset pasa por run (checksum `b3159e9d…24276` re-verificado) |
| hypothesis id | ✅ | `H-MS-01` |
| campaign_id | ⚠️ no es campo del schema | linkage determinístico H-MS-01 → C002 vía catalog.md/campaigns.md (limitación de plataforma; nota R4) |
| seed | ✅ | `0` (y {0,1,2} en la grilla) |

- **R1 — BLOQUEANTE (B3):** el smoke run (celda primaria `0.5/1/both`, seed 0)
  se ejecutó con árbol sucio → `UNVERIFIABLE_REPRODUCTION` → "cannot support
  acceptance". `find_experiments` ordena `created_at ASC` (`store.py:435`) y
  `assemble_trial_matrix.py:69` (`if key not in cells`) toma el primer match →
  la fila `(0.5, 1, both)` de la matriz vendría del smoke run, no del run de
  lanzamiento en árbol limpio. Las series son deterministas (idénticas
  numéricamente), por lo que no hay impacto científico — pero la evidencia
  del veredicto (DSR/RC sobre la matriz) apoyaría formalmente en un run
  no verificable, violando B3.
  **Fix recomendado (al aplicar, en el commit de lanzamiento):** en
  `ordered_cells`, preferir el experimento seed-0 cuyo último run tiene
  `git dirty = false` (o filtrar `env.unverifiable_reproduction`). Re-check
  único de este punto tras el fix.

## Gate 4 — Comparabilidad C001/C002 — PASS

| Dimensión | Evidencia |
|---|---|
| Mismo dataset DS-001 | Ambos usan `es-f-10y-ohlc-v1` (id `8d2a7d6b…9a84`, checksum `b3159e9d…24276`) — configs y código |
| Mismo periodo | Mismo blob → 2,513 barras, 2016-08 → 2026-08 |
| Mismos costes | `cost_bps ∈ {0, 2.5, 5}`, round-trip subtraction — código espejo de C001 |
| Mismos benchmarks | Reuso de los runs C001 del store (E-0002): random_entries 9, buy_hold 1, sma 3, ema 3; sin configs nuevas (`generate_configs.py:24-27`) |
| Mismo tratamiento estadístico | Batería idéntica (perm vs signed pool, Welch, bootstrap, Bayes, SPRT, per-year, vol regime); meta es espejo (N_BOOT=1500, block_size=21) |
| Diferencia única: continuation → fading | Verificado empíricamente: fade `trade_rets ≡ −C001 trade_rets` (`allclose True`); Sharpe +0.1191 vs −0.1191 (celda 0.5/2/both) |

## Gate 5 — Estadística — PASS

- **DSR sobre la grilla completa:** `deflated_sharpe_ratio(best_sharpe,
  trial_sharpes, n_obs, …)` con `trial_sharpes` = los 36 trial means/sharpes
  (`gap_fading_meta.py`); calibración `E-0003` citada en spec §10.
- **White Reality Check:** `reality_check_p_value(trials, block_size=21,
  n_bootstrap=1500)` sobre la matriz completa (36 × n_obs).
- **Sin mejor-Sharpe aislado:** la regla de decisión (spec §12/§13) usa
  DSR + benchmark + robustez; el perm gate es pre-screen explícito (§10).
- **E-0003 (14% nominal ≈ chance):** la tasa de significancia nominal del
  grid es computable por queries al registry (`p_perm_signal` por célula)
  para el reporte de cierre (nota R6 — no emitida por la meta; no bloqueante).
- **Regla congelada:** ACCEPTED / REJECTED / INCONCLUSIVE /
  REQUIRES_MORE_DATA idénticas en spec §12-§13 y checklist Gate G
  (verificado palabra por palabra).

## Gate 6 — Trial matrix — PASS (condicionado a R1)

- **Conteo planificado:** 38 archivos config → 436 runs atómicos:
  36 células primarias (108 runs @ 0 bps) + 72 células cost (216 @ 2.5/5 bps)
  + 36 delayed (108 @ 0 bps) + meta (3) + smoke (1).
- **Duplicados:** ninguno real — las 145 coincidencias del audit por
  `(module,thr,hold,dir,cost)` corresponden a las 3 seeds por diseño;
  única excepción: el smoke repite la celda primaria `(0.5,1,both)` → R1.
- **Separación por capas (módulos/configs distintos):**
  - primary: `gap_fading` + `config_scan_*` (0 bps)
  - cost sensitivity: `gap_fading` + `config_cost_*` (2.5/5 bps)
  - delayed: `gap_fading_delayed` + `config_delayed_*` (0 bps)
  - meta: `gap_fading_meta` + `config_meta.json` (dataset
    `es-gap-fade-trial-matrix-v1` registrado post-assembly)
  - smoke: `config_smoke.json`
- **Assembly esperado:** 36 filas fade + 36 delayed + benchmarks del store
  (9/1/3/3) + c001 best cell + arrays F-GAP-COMP.

---

## Archivos revisados

- `research_platform/research_studies/gap_fading/campaign_spec.md`
- `research/C002_LAUNCH_CHECKLIST.md`
- `research/feature_registry.md`, `research/features.md`, `research/catalog.md`,
  `research/campaigns.md`, `research/edge_database.md`
- `research_platform/research_studies/gap_fading/{_common,gap_fading,
  gap_fading_delayed,gap_fading_meta,assemble_trial_matrix,generate_configs}.py`
- `research_platform/research_studies/gap_fading/config_*.json` (38)
- `research_platform/research_studies/features/__init__.py`
- `research_platform/research_platform/{runner,config,schema,store,cli,_util}.py`
- `quant_research/{core,statistics,resampling}.py`
- Registry: `research.db` (@ /tmp/research-study), smoke run `9efd8a6a…`

## Riesgos

| ID | Severidad | Descripción | Estado |
|---|---|---|---|
| R1 | **BLOQUEANTE** | Fila `(0.5,1,both)` de la matriz proviene del smoke run en árbol sucio (B3) | Fix de 3 líneas en `assemble_trial_matrix.py` (preferir run seed-0 de árbol limpio) + re-check |
| R2 | Bajo | Convención de exit del delayed no verbatim en spec | Documentada en docstring del módulo; registrar como asunción en el reporte |
| R3 | Bajo | Gap-size buckets no emitidos explícitamente | Derivables de `trial_threshold` en el reporte |
| R4 | Info | `campaign_id` no es campo del schema | Linkage H-MS-01 → C002 determinístico (limitación de plataforma, categoría N) |
| R5 | Info | CLI: `--root` debe ir después del subcomando (`run config --root …`) | Bug de dest duplicado en `cli.py:360-370`; no afecta a la campaña |
| R6 | Info | Tasa nominal (E-0003) no emitida por la meta | Computable por queries al registry para el reporte |

## Decisión

**BLOCKED** — Gates 1, 2, 4, 5 PASS; Gate 3 FAIL por R1; Gate 6 condicionado
a R1. Tras aplicar el fix de R1 (en el commit de lanzamiento, sin cambios de
hipótesis/arquitectura/parámetros) y re-verificar el punto, la campaña queda
**READY_FOR_EXECUTION**, pendiente de aprobación explícita antes de ejecutar
los 436 runs planificados.

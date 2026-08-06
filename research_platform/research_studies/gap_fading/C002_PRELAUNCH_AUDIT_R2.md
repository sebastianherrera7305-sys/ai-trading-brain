# C002 PRE-LAUNCH AUDIT — R2 — R1 Resolution (evidence selection)

**Role:** Director of Quantitative Research.
**Date:** 2026-08-06.
**Scope:** resolve the single blocking item (R1) of
`C002_PRELAUNCH_AUDIT.md` and re-validate. No C002 experiments executed.
No hypothesis/parameter/statistical-methodology changes. C001 untouched.
Smoke run preserved (append-only store). No destructive cleanup.

---

## Antes — R1 BLOCKED

El smoke run (celda `(0.5, 1, both)`, seed 0, commit `bcfe4ed`, árbol
sucio → `UNVERIFIABLE_REPRODUCTION`) aparecía primero en
`find_experiments` (`created_at ASC`) y `assemble_trial_matrix.py`
seleccionaba el primer match → la fila de la matriz (input de
DSR/Reality Check) podía provenir de un run no elegible como evidencia
(B3: "cannot support acceptance").

## Después — R1 PASS

El trial matrix selecciona únicamente runs elegibles y registra (sin
ocultar) todos los descartes.

### Criterios implementados

1. **Excluye:** runs con `UNVERIFIABLE_REPRODUCTION`, env `git.dirty`,
   record `git_dirty=True`, `status != completed`, sin run, sin env
   snapshot (metadata incompleta).
2. **Prefiere:** clean tree + completed + seed-0 explícito (por celda)
   + metadata completa (env con git state).
3. **Trazabilidad:** cada candidato excluido se imprime con celda, uuid
   y razón; el smoke run sigue existiendo en el store (nada se borra).

### Evidencia

- **Archivo modificado (único):**
  `research_platform/research_studies/gap_fading/assemble_trial_matrix.py`
  - `:27` — docstring: política de selección de evidencia (B3).
  - `:67` — `_is_eligible_run(store, exp)` → `(ok, reason)` — gate de
    elegibilidad (completo, clean, metadata completa; excluye
    UNVERIFIABLE/dirty/failed).
  - `:97` — `_report_discards(tag, discarded)` — registro de descartes.
  - `:120` — `ordered_cells(...)` — selección seed-0 con gate de
    elegibilidad; célula sin candidato elegible → **refusal**
    ("missing eligible … ineligible candidates were excluded").
  - `:152` — mensaje de refusal con trazabilidad.
  - `:160` — `best_c001_cell(...)` — mismo gate (runs C001 no
    modificados, solo lectura).
  - `:209` — `rows(...)` (benchmarks random/buyhold/sma/ema) — mismo gate.

- **Tests (nuevos):** `research_platform/tests/test_gap_fading_assembly.py`
  — 9 tests: acepta clean/completed; rechaza UNVERIFIABLE, dirty-env,
  failed, sin run, sin env, record dirty; `ordered_cells` prefiere el
  clean sobre el smoke (y reporta el descarte del smoke); refusal
  cuando el único candidato es no elegible.
  Resultado: **9/9 PASS**; suite completa **110/110 PASS** (101 previos
  + 9 nuevos).

- **Validación trial matrix (dry-run, sin ejecución)** contra el store
  real (`/tmp/research-study`):

  ```
  evidence selection: 1 gap_fading candidate(s) excluded:
    cell=(0.5, 1, 'both') exp=9efd8a6a -> UNVERIFIABLE_REPRODUCTION
      (dirty tree at execution, commit bcfe4ed385e576ece6195aea71ad2261e7260ede)
  EXPECTED: missing eligible gap_fading cells: ([…36 células…])
    (ineligible candidates were excluded; see discarded list above)
  ```

  → El smoke run `9efd8a6a` queda **excluido con razón registrada** y la
  matriz **se niega** a construirse con evidencia no elegible (faltan
  los runs de lanzamiento en árbol limpio — correcto).

### Confirmación C001 intacto

- `git status`: 0 archivos tocados en `research_studies/gap_continuation/`.
- El assembly solo LEE runs C001 (benchmarks + mejor célula) a través
  del mismo gate de lectura; ningún archivo C001 fue modificado.
- El smoke run histórico sigue en el store (append-only, sin limpieza).

### Notas

- El fix no altera hipótesis, parámetros, ni metodología estadística;
  solo la selección de qué run alimenta la matriz (corrección de
  evidencia, B3).
- Tras el lanzamiento (árbol limpio), las 36 células tendrán runs
  elegibles y el assembly seleccionará el run seed-0 de árbol limpio
  incluso si el smoke existiera en la misma celda.

---

## Gates (post-fix)

| Gate | Estado |
|---|---|
| 1. Protocolo científico | PASS (sin cambios) |
| 2. Ausencia de leakage | PASS (sin cambios) |
| 3. Reproducibilidad | **PASS** (R1 resuelto) |
| 4. Comparabilidad C001/C002 | PASS (sin cambios) |
| 5. Estadística | PASS (sin cambios) |
| 6. Trial matrix | **PASS** (selección de evidencia corregida y probada) |

## Decisión final

**READY_FOR_EXECUTION** — todos los gates PASS.

**STOP.** No se lanza C002. No se ejecuta el batch (436 runs), ni DSR,
ni Reality Check reales. Pendiente de aprobación explícita del Director
antes de la secuencia de lanzamiento (commit de lanzamiento → grid →
assembly → meta).

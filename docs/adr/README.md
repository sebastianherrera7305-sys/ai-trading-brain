# Architecture Decision Records

`docs/ARCHITECTURE.md` (v1.0, frozen) is the contract. Any implementation
choice that would add/modify/couple a module in a way the eight questions
flag as concerning gets an ADR here first — proposed, discussed, accepted
or rejected, *then* implemented. The ADD itself is not edited directly
after v1.0; an accepted ADR that changes the architecture gets folded
back into the ADD as a dated revision, but the reasoning trail lives here.

Use `TEMPLATE.md` for new entries. Numbered sequentially, never reused.

## Log

| ADR | Title | Status |
|---|---|---|
| [0001](0001-unified-storage-engine.md) | Unified storage engine: DuckDB from the start, not SQLite-then-migrate | Accepted |

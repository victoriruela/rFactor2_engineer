# ROADMAP - MoTeC LD WASM Parser (Agentic Kanban)

## Scope and Guardrails
- Objective: Build a client-side MoTeC `.ld` parser using Rust + WASM + Web Worker orchestration with zero/near-zero allocation across JS/WASM boundary.
- Non-goals for this phase: No production UI polish, no backend persistence changes, no server-side telemetry parsing.
- Hard constraints:
  - Never parse on main thread.
  - Never `file.arrayBuffer()` full-file load for 50MB-100MB files.
  - Never emit channel arrays as JSON.
  - Memory exchange must use WASM pointer + typed array views.

## Board Model
- `Pending`: Defined and ready, not started.
- `In Progress`: Assigned to one implementation subagent.
- `On Hold`: Blocked by dependency or integration issue.
- `Done`: Integrated, validated, and documented.

## Dependency Graph (summary)
- R1 -> R2 -> R3 -> R4 -> R5
- R2.T3 and R2.T4 can run in parallel after R2.T2.
- R4.T2 can start only after R3.T2.
- R5.T1 can start once R4.T1 is done.

---

## Stage 1 - Binary Format Research Validation

### Card R1.T1 - LD3/LD4 header map validation
- Kanban: `Pending`
- Owner profile: `Explore` subagent (research-heavy)
- Priority: P0
- Estimate: 0.5d
- Depends on: none
- Deliverables:
  - `docs/ld_format_research.md` section for header signatures, endian rules, absolute offsets.
  - Byte-level table for LD3 and LD4 known/assumed fields.
- Subagent implementation brief:
  - Collect public reverse-engineering references and reconcile conflicts.
  - Produce one canonical struct table with confidence levels per field (High/Medium/Low).
  - Include parser-safe fallback behavior for unknown fields.
- Definition of done:
  - Includes magic/version detection rules.
  - Includes all offsets needed to locate channel meta region and data region.
  - Includes explicit little-endian decoding strategy.
- Validation:
  - Cross-check at least 2 independent references for each critical offset.

### Card R1.T2 - Channel meta struct and datatype map
- Kanban: `Pending`
- Owner profile: parser subagent
- Priority: P0
- Estimate: 0.5d
- Depends on: R1.T1
- Deliverables:
  - `docs/ld_format_research.md` section for channel meta struct layout.
  - Type mapping table: identifier byte -> Rust primitive -> JS typed array.
- Subagent implementation brief:
  - Define exact fields: channel name, short name, units, sample rate, sample count, data type, data offset.
  - Define conversion matrix and unsupported types behavior.
- Definition of done:
  - Every mapped type includes size in bytes and signed/unsigned semantics.
  - Unsupported types documented with deterministic error code strategy.

---

## Stage 2 - Rust Core Skeleton (Parser Library)

### Card R2.T1 - Scaffold Rust parser crate (non-WASM first)
- Kanban: `Pending`
- Owner profile: wasm systems subagent
- Priority: P0
- Estimate: 0.5d
- Depends on: R1.T2
- Deliverables:
  - `wasm/ld_parser/Cargo.toml`
  - `wasm/ld_parser/src/lib.rs`
  - `wasm/ld_parser/src/error.rs`
  - `wasm/ld_parser/src/types.rs`
- Subagent implementation brief:
  - Create clean domain model (`MainHeader`, `ChannelMeta`, `DataType`, `ParseError`).
  - Keep crate WASM-agnostic.
  - Prohibit `unwrap()` outside tests.
- Definition of done:
  - `cargo test` runs with zero tests failing.
  - Public APIs compile and expose parser entrypoints stubs.

### Card R2.T2 - Implement `nom` main header parser
- Kanban: `Pending`
- Owner profile: parser subagent
- Priority: P0
- Estimate: 1d
- Depends on: R2.T1
- Deliverables:
  - `wasm/ld_parser/src/parser/header.rs`
  - Unit tests for valid + invalid headers.
- Subagent implementation brief:
  - Implement composable nom parsers for signature/version/offset fields.
  - Return rich typed errors for bad magic, short buffers, unsupported version.
- Definition of done:
  - Tests include malformed and truncated fixtures.
  - Header parse has deterministic error variants.

### Card R2.T3 - Implement `nom` channel meta parser
- Kanban: `Pending`
- Owner profile: parser subagent
- Priority: P0
- Estimate: 1d
- Depends on: R2.T2
- Deliverables:
  - `wasm/ld_parser/src/parser/channel.rs`
  - Test fixtures for multi-channel metadata.
- Subagent implementation brief:
  - Parse channel records and normalize strings/units.
  - Validate data offsets/length do not overflow `u64` calculations.
- Definition of done:
  - Can parse at least one synthetic multi-channel sample.
  - Fails safely on out-of-bounds offsets.

### Card R2.T4 - Mock binary fixture suite
- Kanban: `Pending`
- Owner profile: test subagent
- Priority: P1
- Estimate: 0.5d
- Depends on: R2.T2
- Deliverables:
  - `wasm/ld_parser/tests/fixtures/*.ldbin`
  - `wasm/ld_parser/tests/parser_tests.rs`
- Subagent implementation brief:
  - Build deterministic binary fixtures for happy path and failure classes.
  - Keep fixtures tiny and documented byte-by-byte.
- Definition of done:
  - Fixtures cover version mismatch, truncated blocks, unknown datatype.

---

## Stage 3 - WASM Binding Layer

### Card R3.T1 - Introduce wasm-bindgen wrapper
- Kanban: `Pending`
- Owner profile: wasm systems subagent
- Priority: P0
- Estimate: 0.5d
- Depends on: R2.T3, R2.T4
- Deliverables:
  - `wasm/ld_parser_wasm/Cargo.toml`
  - `wasm/ld_parser_wasm/src/lib.rs`
- Subagent implementation brief:
  - Wrap pure parser crate without leaking implementation internals.
  - Export stable ABI-like functions for headers and channel extraction metadata.
- Required signatures (initial):
  - `parse_headers(buffer: &[u8]) -> Result<String, JsValue>`
  - `prepare_channel_decode(buffer: &[u8], dtype: u8) -> Result<DecodeHandle, JsValue>`
- Definition of done:
  - WASM builds in debug and release profiles.

### Card R3.T2 - Pointer-based memory API design
- Kanban: `Pending`
- Owner profile: wasm systems subagent
- Priority: P0
- Estimate: 1d
- Depends on: R3.T1
- Deliverables:
  - Exported functions for pointer/length retrieval and explicit free.
  - `docs/wasm_memory_contract.md`
- Subagent implementation brief:
  - Implement deterministic allocation lifecycle:
    - decode bytes -> write contiguous typed buffer in linear memory
    - return `{ptr, len, kind}`
    - require explicit `free_buffer(ptr, len, kind)`
  - Define JS-side rules to avoid stale views after free.
- Definition of done:
  - No JSON serialization of full channel series.
  - Demonstrated Float32 path with pointer view.

---

## Stage 4 - JS Web Worker Orchestration

### Card R4.T1 - Worker protocol and message contracts
- Kanban: `Pending`
- Owner profile: frontend platform subagent
- Priority: P0
- Estimate: 0.5d
- Depends on: R3.T1
- Deliverables:
  - `apps/expo_app/src/workers/parser.worker.ts`
  - `apps/expo_app/src/workers/protocol.ts`
- Subagent implementation brief:
  - Define strict TypeScript discriminated unions for all worker messages.
  - Implement init/parseHeaders/extractChannel/error events.
- Definition of done:
  - No `any` types in worker protocol.

### Card R4.T2 - Lazy `File.slice()` extraction pipeline
- Kanban: `Pending`
- Owner profile: frontend platform subagent
- Priority: P0
- Estimate: 1d
- Depends on: R4.T1, R3.T2
- Deliverables:
  - Slice-by-offset implementation for header and channel chunks.
  - Backpressure-safe async queue for repeated channel requests.
- Subagent implementation brief:
  - Read first chunk only for headers.
  - Resolve exact byte spans for selected channels.
  - Ensure no full-file `arrayBuffer()` calls.
- Definition of done:
  - Proven by code path inspection and debug logs.

### Card R4.T3 - WASM pointer -> TypedArray adapter
- Kanban: `Pending`
- Owner profile: frontend platform subagent
- Priority: P0
- Estimate: 0.5d
- Depends on: R4.T2
- Deliverables:
  - Adapter utility mapping `{ptr, len, kind}` to typed views.
  - Safety checks for memory bounds and free lifecycle.
- Subagent implementation brief:
  - Implement `Float32Array` and `Int32Array` paths.
  - Add defensive checks for detached/invalid memory windows.
- Definition of done:
  - Adapter supports zero-copy view creation for large channels.

---

## Stage 5 - UI and Render Integration

### Card R5.T1 - Rendering engine benchmark decision (uPlot vs WebGL)
- Kanban: `Pending`
- Owner profile: frontend perf subagent
- Priority: P1
- Estimate: 0.5d
- Depends on: R4.T1
- Deliverables:
  - `docs/render_benchmark.md`
  - Recommendation with rationale (frame stability, memory, integration cost).
- Subagent implementation brief:
  - Benchmark on at least 100k and 500k point series.
  - Capture render time and interaction latency.
- Definition of done:
  - Explicit recommendation and fallback option.

### Card R5.T2 - Async UI state machine for parse flow
- Kanban: `Pending`
- Owner profile: frontend feature subagent
- Priority: P1
- Estimate: 1d
- Depends on: R4.T3, R5.T1
- Deliverables:
  - State machine: `idle -> loading_headers -> selecting_channels -> decoding -> rendering -> error`.
  - UI wiring in telemetry flow with non-blocking transitions.
- Subagent implementation brief:
  - Keep UI responsive with cancellable channel decode requests.
  - Surface precise errors from worker parser.
- Definition of done:
  - Manual test confirms no main-thread freeze during 500k sample render.

---

## Supervisor Dispatch Plan (First Two Waves)

### Wave 1 (parallelizable)
- R1.T1 (research)
- R1.T2 (starts as soon as R1.T1 is merged)

### Wave 2 (parallelizable)
- R2.T1
- R2.T2
- R2.T4 (after R2.T2)
- R2.T3 (after R2.T2, independent from R2.T4)

## Global Acceptance Criteria
- Parsing and channel extraction run entirely off main thread.
- 100MB `.ld` flow does not trigger full-file heap allocation.
- Telemetry arrays are not serialized as JSON.
- Pointer-based typed array mapping documented and tested.
- Quality gates pass for touched modules.

## Quality Gates per Task
- Rust parser tasks:
  - `cargo test`
  - `cargo clippy --all-targets -- -D warnings`
  - `cargo build --release`
- Frontend tasks:
  - `npx expo lint`
  - `npm test`
  - `npx expo export -p web`

## Asana Mapping Convention
- Task names use card IDs, e.g., `R2.T3 Implement nom channel meta parser`.
- Description template must include:
  - Scope
  - Dependencies
  - DoD
  - Validation commands
  - Expected artifacts


# SPECIFICATION: High-Performance Client-Side MoTeC `.ld` Telemetry Parser

## 1. Architectural Overview & Context
This specification outlines the architecture for a zero-copy (or near zero-copy), memory-safe, and non-blocking telemetry parser running entirely within a web browser environment. We are abandoning the bloated MATLAB `.mat` (v7.3/HDF5) format (which routinely exceeds 700MB) in favor of the industry-standard MoTeC `.ld` binary format. 

The primary objective is to process 50MB-100MB binary files locally on the client machine without triggering Main Thread UI freezes, Garbage Collection (GC) stutters, or Out-Of-Memory (OOM) exceptions. Given the target environment, we will utilize a dual-engine architecture: a JavaScript/TypeScript orchestration layer in the main thread/web worker, and a WebAssembly (WASM) core compiled from Rust (or Go, though Rust is preferred for deterministic memory management and `no_std` capabilities) to handle the intense binary decoding.

## 2. The Format: MoTeC `.ld` Binary Layout
The `.ld` file is a proprietary but heavily reverse-engineered binary format. It is fundamentally a header-pointer structure, making it ideal for lazy loading via the `File.slice()` API.

### 2.1 Block Structure
An `.ld` file generally consists of three primary regions:
1.  **Main Header:** Contains the magic string (`"LD" ` or `"LD3"`), file version, and global metadata (vehicle info, venue, date, driver). Crucially, it contains absolute byte offsets pointing to the Channel Meta Block and the Data Block.
2.  **Channel Meta Block:** An array of structs defining every available telemetry channel. Each struct includes:
    * Channel Name (e.g., `GForceX`, `EngineRPM`)
    * Short Name
    * Unit of Measurement (e.g., `G`, `rpm`)
    * Sampling Frequency (Hz)
    * Data Type (e.g., 16-bit signed integer, 32-bit float)
    * Total Samples Count
    * **Data Offset:** The absolute byte offset where this specific channel's contiguous data array begins.
3.  **Data Block:** The raw, uncompressed bytes. Unlike CSV or JSON, this data is heavily packed.

### 2.2 Endianness
MoTeC files are universally Little-Endian. The Rust parser must explicitly use Little-Endian decoding (e.g., via the `byteorder` or `nom` crates) to avoid architecture-dependent bugs when compiled to `wasm32-unknown-unknown`.

## 3. Implementation Strategy: The "Lazy WASM" Pattern

### Phase 1: Main Thread Orchestration (File Selection)
When the user selects an `.ld` file via `Ningún archivo seleccionado`, we DO NOT call `file.arrayBuffer()`. Doing so would immediately allocate the entire file into the V8 heap.
Instead, we retain the `File` object (which is just a pointer to the OS file system buffer).

### Phase 2: The Web Worker Boundary
The `File` object is passed to a dedicated Web Worker (`parser.worker.ts`). All Rust/WASM initialization occurs within this worker. This ensures that even if the WASM module blocks execution for 200ms while parsing headers, the DOM remains perfectly responsive at 60fps.

### Phase 3: Header Slicing & Initial Parse
The worker reads only the first ~10KB of the file using `const slice = file.slice(0, 10240); const buffer = await slice.arrayBuffer();`.
This tiny `ArrayBuffer` is passed across the WASM boundary.
The Rust core parses the Main Header and the Channel Meta Block.
Rust serializes the channel list (Names, Units, Frequencies) into a lightweight JSON string and passes it back to the JS UI. The UI now renders a checklist of available telemetry channels.

### Phase 4: On-Demand Data Extraction (Zero-Copy Goal)
When a user selects "View EngineRPM" (which the metadata indicates is 500,000 float32 samples):
1.  The JS Worker looks up the exact byte offset and byte length for `EngineRPM`.
2.  JS slices exactly that portion: `file.slice(offset, offset + length)`.
3.  The slice is resolved to an `ArrayBuffer` and passed to WASM.
4.  **Critical Performance Step:** Rust parses the raw bytes. Instead of serializing an array of 500,000 floats into JS objects (which would kill the garbage collector), Rust writes the floats into a contiguous block of WASM linear memory.
5.  Rust returns the memory pointer (offset) and length to JS.
6.  JS creates a `Float32Array` view *directly* over the WASM memory buffer: `new Float32Array(wasmMemory.buffer, pointer, length)`.
7.  This array is sent to the charting library (e.g., uPlot) or WebGL canvas. Zero JS objects were created. Zero GC pressure was added.

## 4. Technology Stack
* **WASM Core:** Rust (Edition 2021).
* **Rust Crates:** `wasm-bindgen` (for JS interop), `nom` (for safe, combinator-based binary parsing), `js-sys` and `web-sys` (if direct DOM/Worker manipulation from Rust is desired, though keeping Rust pure and wrapping it in JS is preferred for decoupling).
* **Frontend/Orchestration:** TypeScript, Web Workers, Vite (for built-in WASM support).
* **Visualization:** uPlot or custom WebGL (Canvas API). Do NOT use Chart.js or Recharts for 500k+ data points.

## 5. Security & Isolation Constraints
* **Cross-Origin Isolation:** If we wish to utilize `SharedArrayBuffer` for synchronous multi-threading (e.g., using `rayon` in WASM), the server MUST emit `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp` headers. 
* **Fallback:** The architecture must gracefully degrade to standard asynchronous `ArrayBuffer` transfer semantics if COOP/COEP headers are unavailable (e.g., in a local Dev environment without a configured server).

---

## NEXT STEPS FOR AGENT: Converting to ROADMAP.md

To the AI Agent receiving this specification: Your immediate task is to ingest this document and output a comprehensive `ROADMAP.md`. You must perform contextual research on the MoTeC `.ld` binary layout and synthesize it with the architectural directives above.

**Your `ROADMAP.md` must contain the following stages:**

1.  **Stage 1: Binary Format Research Validation**
    * Create a sub-task to define the exact byte offsets for the LD3/LD4 headers. Define the struct layouts for the Channel Meta Block. Document known data types (short, int, float) mapped to their MoTeC identifier bytes.

2.  **Stage 2: Rust Core Skeleton (The Parser Library)**
    * Define tasks to scaffold a standard Rust library (agnostic to WASM initially).
    * Task for implementing the `nom` parsers for the Main Header.
    * Task for implementing the `nom` parsers for the Channel Headers.
    * Task for writing unit tests using a mock `.ld` file byte array.

3.  **Stage 3: WASM Binding Layer**
    * Define tasks to wrap the Rust library with `wasm-bindgen`.
    * Create the exact function signatures required (e.g., `pub fn parse_headers(buffer: &[u8]) -> String`, `pub fn extract_channel(buffer: &[u8], data_type: u8) -> *const f32`).
    * Document the memory allocation strategy for exposing pointers to JS.

4.  **Stage 4: JS Web Worker Orchestration**
    * Define the Web Worker setup.
    * Task for implementing the `File.slice()` logic based on the byte offsets returned from the header parse.
    * Task for mapping WASM memory pointers to `Float32Array` views.

5.  **Stage 5: UI & Render Integration**
    * Task for selecting a high-performance rendering engine (evaluate uPlot vs WebGL).
    * Task for handling the asynchronous UI state (Loading headers -> Selecting channels -> Rendering data).

Do not begin writing code until `ROADMAP.md` is generated, reviewed, and approved by the architect. Use your internal knowledge base to fill in the gaps regarding `nom` combinators and `wasm-bindgen` memory management.
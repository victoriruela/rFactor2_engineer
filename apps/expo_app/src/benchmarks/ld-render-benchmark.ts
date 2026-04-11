/**
 * @file ld-render-benchmark.ts
 * @description Client-side render throughput benchmark for WASM-parsed telemetry channels.
 *
 * Measures:
 * - samples/second that can be consumed by a synchronous pass (chart data prep)
 * - frame budget consumption for various channel sizes (1k, 10k, 100k, 1M samples)
 * - zero-alloc path validation: confirms TypedArray views are not copied to plain Arrays
 *
 * Usage (browser console or automated):
 *   import { runBenchmark } from './benchmarks/ld-render-benchmark';
 *   const report = await runBenchmark();
 *   console.table(report.results);
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BenchmarkCase {
  label: string;
  sampleCount: number;
  typeId: number;
}

export interface BenchmarkResult {
  label: string;
  sampleCount: number;
  typeId: number;
  /** Elapsed wall-clock time in milliseconds for the render pass. */
  elapsedMs: number;
  /** Derived: samples processed per second (throughput). */
  samplesPerSec: number;
  /** Estimated % of a 16.67ms frame budget consumed. */
  frameBudgetPct: number;
  /** Whether the TypedArray was a live view (true) or a copy (false — bad). */
  isLiveView: boolean;
}

export interface BenchmarkReport {
  runAt: string;
  userAgent: string;
  results: BenchmarkResult[];
  /** true when ALL cases consumed < 100% of a single frame budget. */
  allWithinFrameBudget: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FRAME_BUDGET_MS = 1000 / 60; // 16.67ms at 60 fps

const DEFAULT_CASES: BenchmarkCase[] = [
  { label: '1k Float32', sampleCount: 1_000, typeId: 0x0000 },
  { label: '10k Float32', sampleCount: 10_000, typeId: 0x0000 },
  { label: '100k Float32', sampleCount: 100_000, typeId: 0x0000 },
  { label: '1M Float32', sampleCount: 1_000_000, typeId: 0x0000 },
  { label: '10k Int16', sampleCount: 10_000, typeId: 0x0001 },
  { label: '100k Uint16', sampleCount: 100_000, typeId: 0x0002 },
];

// ---------------------------------------------------------------------------
// WASM memory simulation (used when real WASM module is not loaded)
// Creates a synthetic backing buffer so the benchmark measures the JS path.
// ---------------------------------------------------------------------------

/** Byte size per sample for a given type_id. */
function sampleByteSize(typeId: number): number {
  switch (typeId) {
    case 0x0000: return 4; // Float32
    case 0x0001: return 2; // Int16
    case 0x0002: return 2; // Uint16
    case 0x0003: return 4; // Uint32
    case 0x0004: return 4; // Int32
    case 0x0007: return 8; // Float64
    default: throw new RangeError(`sampleByteSize: unknown typeId 0x${typeId.toString(16)}`);
  }
}

type SupportedTypedArray = Float32Array | Int16Array | Uint16Array | Uint32Array | Int32Array | Float64Array;

/** Construct the TypedArray view matching typeId over the provided buffer. */
function makeTypedView(
  buffer: ArrayBuffer,
  byteOffset: number,
  count: number,
  typeId: number,
): SupportedTypedArray {
  switch (typeId) {
    case 0x0000: return new Float32Array(buffer, byteOffset, count);
    case 0x0001: return new Int16Array(buffer, byteOffset, count);
    case 0x0002: return new Uint16Array(buffer, byteOffset, count);
    case 0x0003: return new Uint32Array(buffer, byteOffset, count);
    case 0x0004: return new Int32Array(buffer, byteOffset, count);
    case 0x0007: return new Float64Array(buffer, byteOffset, count);
    default: throw new RangeError(`makeTypedView: unknown typeId 0x${typeId.toString(16)}`);
  }
}

/**
 * Simulate the WASM memory arena: allocate synthetic sample data in a
 * single ArrayBuffer and return a TypedArray VIEW (not a copy).
 * Writes a sawtooth pattern so the render pass has real data to scan.
 */
function allocateSyntheticChannel(count: number, typeId: number): {
  backing: ArrayBuffer;
  view: SupportedTypedArray;
} {
  const bpe = sampleByteSize(typeId);
  const backing = new ArrayBuffer(count * bpe);
  const view = makeTypedView(backing, 0, count, typeId);
  const period = 100;
  for (let i = 0; i < count; i++) {
    (view as Float32Array)[i] = (i % period) / period;
  }
  return { backing, view };
}

// ---------------------------------------------------------------------------
// Render pass (simulates chart min/max scan — the hot path in telemetry rendering)
// ---------------------------------------------------------------------------

interface MinMax { min: number; max: number; }

/**
 * O(n) min/max scan over a TypedArray — representative of the hottest rendering
 * inner loop (building chart scales, downsampling for canvas painting).
 */
function scanMinMax(view: SupportedTypedArray): MinMax {
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < view.length; i++) {
    const v = (view as Float32Array)[i];
    if (v < min) min = v;
    if (v > max) max = v;
  }
  return { min, max };
}

// ---------------------------------------------------------------------------
// Live-view check
// ---------------------------------------------------------------------------

/**
 * Verify that `view` is a LIVE view (not a copy of) the backing buffer.
 * Writes a sentinel value, checks the backing buffer, then restores.
 */
function checkIsLiveView(backing: ArrayBuffer, view: SupportedTypedArray, typeId: number): boolean {
  if (view.length === 0) return true; // trivially true for empty
  const SENTINEL = 42;
  const original = (view as Float32Array)[0];
  (view as Float32Array)[0] = SENTINEL;
  // Read raw bytes from backing at offset 0
  const probe = makeTypedView(backing, 0, 1, typeId);
  const isLive = (probe as Float32Array)[0] === SENTINEL;
  (view as Float32Array)[0] = original;
  return isLive;
}

// ---------------------------------------------------------------------------
// Core benchmark runner
// ---------------------------------------------------------------------------

/**
 * Run a single benchmark case. Returns timing and metadata.
 */
function runCase(bc: BenchmarkCase): BenchmarkResult {
  const { backing, view } = allocateSyntheticChannel(bc.sampleCount, bc.typeId);
  const isLiveView = checkIsLiveView(backing, view, bc.typeId);

  // Warm up (one pass, not timed)
  scanMinMax(view);

  const t0 = performance.now();
  scanMinMax(view);
  const elapsedMs = performance.now() - t0;

  const samplesPerSec = bc.sampleCount / (elapsedMs / 1000);
  const frameBudgetPct = (elapsedMs / FRAME_BUDGET_MS) * 100;

  return {
    label: bc.label,
    sampleCount: bc.sampleCount,
    typeId: bc.typeId,
    elapsedMs,
    samplesPerSec,
    frameBudgetPct,
    isLiveView,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Run the full benchmark suite and return a typed report.
 * Async to avoid blocking the main thread between cases (yields via setTimeout).
 */
export async function runBenchmark(cases: BenchmarkCase[] = DEFAULT_CASES): Promise<BenchmarkReport> {
  const results: BenchmarkResult[] = [];

  for (const bc of cases) {
    // Yield to microtask queue between cases to avoid jank during interactive use.
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    results.push(runCase(bc));
  }

  const allWithinFrameBudget = results.every((r) => r.frameBudgetPct < 100);

  return {
    runAt: new Date().toISOString(),
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'non-browser',
    results,
    allWithinFrameBudget,
  };
}

/**
 * Pretty-print a benchmark report to the console.
 * Call after runBenchmark() for a readable summary during development.
 */
export function printReport(report: BenchmarkReport): void {
  console.log(`=== ld-render-benchmark @ ${report.runAt} ===`);
  console.log(`UA: ${report.userAgent}`);
  console.table(
    report.results.map((r) => ({
      label: r.label,
      samples: r.sampleCount.toLocaleString(),
      'ms': r.elapsedMs.toFixed(3),
      'M samp/s': (r.samplesPerSec / 1e6).toFixed(2),
      'frame%': r.frameBudgetPct.toFixed(1) + '%',
      liveView: r.isLiveView ? '✓' : '✗ COPY DETECTED',
    }))
  );
  console.log(`All within frame budget: ${report.allWithinFrameBudget}`);
}

/**
 * @file wasm-typed-array-adapter.ts
 * @description Zero-copy TypedArray adapter for WASM linear memory.
 *
 * ## Zero-Copy Contract
 * After `LOAD_CHANNEL_DATA_OK`, the Worker returns a raw WASM memory pointer.
 * This module constructs a VIEW (not a copy) over `wasm.memory.buffer` using that pointer.
 *
 * The view is live: if WASM code writes to the same region the view will see the change.
 * The view becomes invalid (detached) if `wasm.memory` grows (triggers a new ArrayBuffer).
 * Always reconstruct the view from ptr after any WASM call that could allocate.
 */

import type { LoadChannelDataResponse } from './worker-protocol';

// ---------------------------------------------------------------------------
// Type mapping
// ---------------------------------------------------------------------------

/** Maps wasm type_id to the equivalent JS TypedArray constructor. */
export const TYPE_ID_TO_CTOR: Readonly<Record<number, new (buf: ArrayBuffer, offset: number, length: number) => ArrayBufferView>> = {
  0x0000: Float32Array,
  0x0001: Int16Array,
  0x0002: Uint16Array,
  0x0003: Uint32Array,
  0x0004: Int32Array,
  0x0007: Float64Array,
} as const;

// ---------------------------------------------------------------------------
// Main adapter — wraps a WASM memory pointer as a live TypedArray view
// ---------------------------------------------------------------------------

export interface ChannelView {
  /** Channel name for display. */
  readonly channelName: string;
  /** Typed array view over WASM linear memory. Zero copy. */
  readonly samples: Float32Array | Int16Array | Uint16Array | Uint32Array | Int32Array | Float64Array;
  /** Raw WASM pointer (byte offset into wasm.memory.buffer). Needed to call FREE. */
  readonly ptr: number;
  readonly count: number;
  readonly typeId: number;
}

/**
 * Construct a live zero-copy TypedArray view over WASM linear memory.
 *
 * @param wasmMemoryBuffer  `wasm.memory.buffer` — the WASM linear memory ArrayBuffer.
 * @param msg               The `LOAD_CHANNEL_DATA_OK` Worker response.
 * @param channelName       Display name (from ChannelInfo).
 *
 * @returns ChannelView with `.samples` pointing directly into WASM memory.
 * @throws  If type_id is not in TYPE_ID_TO_CTOR.
 */
export function makeChannelView(
  wasmMemoryBuffer: ArrayBuffer,
  msg: LoadChannelDataResponse,
  channelName: string,
): ChannelView {
  const Ctor = TYPE_ID_TO_CTOR[msg.typeId];
  if (!Ctor) {
    throw new TypeError(
      `makeChannelView: unknown type_id 0x${msg.typeId.toString(16).padStart(4, '0')} for channel "${channelName}"`,
    );
  }

  // Construct view at exact byte offset — zero copy.
  const samples = new Ctor(wasmMemoryBuffer, msg.ptr, msg.count) as ChannelView['samples'];

  return { channelName, samples, ptr: msg.ptr, count: msg.count, typeId: msg.typeId };
}

// ---------------------------------------------------------------------------
// Typed accessor helpers
// ---------------------------------------------------------------------------

/** Narrow a ChannelView's samples to Float32Array. Throws if wrong type. */
export function asFloat32(view: ChannelView): Float32Array {
  if (view.typeId !== 0x0000) {
    throw new TypeError(`asFloat32: channel "${view.channelName}" has type_id 0x${view.typeId.toString(16)}`);
  }
  return view.samples as Float32Array;
}

/** Returns the minimum value in the channel's sample buffer. O(n), no allocation. */
export function channelMin(view: ChannelView): number {
  const { samples } = view;
  let min = Infinity;
  for (let i = 0; i < samples.length; i++) {
    // TypedArrays all support numeric indexing
    const v = (samples as Float32Array)[i];
    if (v < min) min = v;
  }
  return min;
}

/** Returns the maximum value. O(n), no allocation. */
export function channelMax(view: ChannelView): number {
  const { samples } = view;
  let max = -Infinity;
  for (let i = 0; i < samples.length; i++) {
    const v = (samples as Float32Array)[i];
    if (v > max) max = v;
  }
  return max;
}

/** Returns [min, max] in one pass. O(n), no allocation. */
export function channelMinMax(view: ChannelView): [number, number] {
  const { samples } = view;
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < samples.length; i++) {
    const v = (samples as Float32Array)[i];
    if (v < min) min = v;
    if (v > max) max = v;
  }
  return [min, max];
}

// ---------------------------------------------------------------------------
// Worker client helper — sends requests and awaits typed responses
// ---------------------------------------------------------------------------

import type { WorkerRequest, WorkerResponse } from './worker-protocol';

/**
 * Thin typed wrapper around a Worker.
 * Sends requests and resolves Promises when the matching response arrives.
 * All communication is via the typed WorkerRequest / WorkerResponse protocol.
 */
export class LdParserWorkerClient {
  private readonly worker: Worker;
  private readonly pending = new Map<string, {
    resolve: (res: WorkerResponse) => void;
    reject: (err: Error) => void;
  }>();

  constructor(workerScriptUrl: string | URL) {
    this.worker = new Worker(workerScriptUrl, { type: 'module' });
    this.worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const res = event.data;
      const entry = this.pending.get(res.id);
      if (!entry) return; // stale or unsolicited
      this.pending.delete(res.id);
      if (res.kind === 'ERROR') {
        entry.reject(new Error(res.message));
      } else {
        entry.resolve(res);
      }
    };
    this.worker.onerror = (err) => {
      // Propagate worker-level errors to all pending requests.
      for (const [, entry] of this.pending) {
        entry.reject(new Error(`Worker error: ${err.message}`));
      }
      this.pending.clear();
    };
  }

  /** Send a request and return a promise that resolves with the matching response. */
  send(request: WorkerRequest): Promise<WorkerResponse> {
    return new Promise<WorkerResponse>((resolve, reject) => {
      this.pending.set(request.id, { resolve, reject });
      this.worker.postMessage(request);
    });
  }

  /** Terminate the Worker and cancel all pending requests. */
  terminate(): void {
    this.worker.terminate();
    for (const [, entry] of this.pending) {
      entry.reject(new Error('Worker terminated'));
    }
    this.pending.clear();
  }
}

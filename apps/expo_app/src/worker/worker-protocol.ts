/**
 * @file worker-protocol.ts
 * @description Typed message protocol for the MoTeC .ld parser Web Worker.
 *
 * All cross-thread messages MUST use these interfaces.
 * No `any` types. Strict mode enforced.
 *
 * ## Design Contract
 * - Main thread sends `WorkerRequest` messages to the Worker.
 * - Worker replies with `WorkerResponse` messages (same `id` round-tripped).
 * - Large data (channel samples) is NEVER serialized to JSON.
 *   Instead, the Worker returns a raw pointer + length; the main thread
 *   constructs a TypedArray VIEW over `wasm.memory.buffer` — zero copy.
 * - On error, the Worker returns `WorkerErrorResponse`.
 */

// ---------------------------------------------------------------------------
// Request types (Main → Worker)
// ---------------------------------------------------------------------------

/** Parse the file header from the first slice of the file. */
export interface ParseHeaderRequest {
  readonly kind: 'PARSE_HEADER';
  /** Unique correlation ID — echoed back in the response. */
  readonly id: string;
  /** Raw bytes of the file header region (at minimum 0x200 bytes). */
  readonly headerBytes: Uint8Array;
}

/** Parse all channel metadata records. */
export interface ParseChannelsRequest {
  readonly kind: 'PARSE_CHANNELS';
  readonly id: string;
  /**
   * Bytes covering the region [0 .. channel_meta_offset + channel_meta_size].
   * Typically obtained via File.slice(0, channel_meta_offset + channel_meta_size).
   */
  readonly metaBytes: Uint8Array;
  /** Absolute byte offset of first channel record (from ParseHeaderResponse). */
  readonly firstMetaOffset: number;
}

/**
 * Load raw sample data for one channel into WASM linear memory.
 * JS side will then build a zero-copy TypedArray view.
 */
export interface LoadChannelDataRequest {
  readonly kind: 'LOAD_CHANNEL_DATA';
  readonly id: string;
  /** Raw bytes for the channel's data region: File.slice(data_offset, data_offset + data_byte_len). */
  readonly dataBytes: Uint8Array;
  /** Absolute file offset for this channel's data (from JsChannelInfo.data_offset). */
  readonly dataOffset: number;
  /** Number of samples. */
  readonly count: number;
  /** WASM type_id (0x0000=f32, 0x0001=i16, etc.) */
  readonly typeId: number;
}

/** Free a previously allocated WASM buffer. MUST be called when done with a channel. */
export interface FreeChannelBufferRequest {
  readonly kind: 'FREE_CHANNEL_BUFFER';
  readonly id: string;
  readonly ptr: number;
  readonly count: number;
  readonly typeId: number;
}

export type WorkerRequest =
  | ParseHeaderRequest
  | ParseChannelsRequest
  | LoadChannelDataRequest
  | FreeChannelBufferRequest;

// ---------------------------------------------------------------------------
// Response types (Worker → Main)
// ---------------------------------------------------------------------------

/** Parsed session info from the file header. */
export interface ParseHeaderResponse {
  readonly kind: 'PARSE_HEADER_OK';
  readonly id: string;
  readonly version: number;
  readonly channelMetaOffset: number;
  readonly dataOffset: number;
  readonly session: string;
  readonly venue: string;
  readonly vehicle: string;
  readonly driver: string;
  readonly date: string;
}

/** Metadata for one channel. */
export interface ChannelInfo {
  readonly name: string;
  readonly shortName: string;
  readonly units: string;
  readonly sampleRate: number;
  readonly count: number;
  readonly typeId: number;
  readonly dataOffset: number;
  readonly dataByteLen: number;
}

/** List of all parsed channel descriptors. */
export interface ParseChannelsResponse {
  readonly kind: 'PARSE_CHANNELS_OK';
  readonly id: string;
  readonly channels: readonly ChannelInfo[];
}

/**
 * Response after loading channel data into WASM linear memory.
 *
 * The main thread uses `ptr` + `count` + `typeId` to build a zero-copy view:
 * ```ts
 * const view = new Float32Array(wasm.memory.buffer, msg.ptr, msg.count);
 * ```
 * Call FreeChannelBufferRequest when done.
 */
export interface LoadChannelDataResponse {
  readonly kind: 'LOAD_CHANNEL_DATA_OK';
  readonly id: string;
  /** Raw pointer (byte offset) into `wasm.memory.buffer`. */
  readonly ptr: number;
  readonly count: number;
  readonly typeId: number;
  /** JS TypedArray constructor name for this channel (e.g. "Float32Array"). */
  readonly typedArrayName: string;
}

export interface FreeChannelBufferResponse {
  readonly kind: 'FREE_CHANNEL_BUFFER_OK';
  readonly id: string;
}

/** Worker-level error reply. */
export interface WorkerErrorResponse {
  readonly kind: 'ERROR';
  /** Correlation ID of the request that caused this error. */
  readonly id: string;
  readonly message: string;
}

export type WorkerResponse =
  | ParseHeaderResponse
  | ParseChannelsResponse
  | LoadChannelDataResponse
  | FreeChannelBufferResponse
  | WorkerErrorResponse;

// ---------------------------------------------------------------------------
// ID generator helper
// ---------------------------------------------------------------------------

let _seq = 0;

/** Generate a unique correlation ID for a Worker request. */
export function nextRequestId(prefix = 'req'): string {
  return `${prefix}-${Date.now()}-${++_seq}`;
}

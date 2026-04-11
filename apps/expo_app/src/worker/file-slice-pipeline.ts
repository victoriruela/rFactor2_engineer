/**
 * @file file-slice-pipeline.ts
 * @description Lazy File.slice pipeline for zero-copy .ld data ingestion.
 *
 * ## Core Principle
 * A .ld file can be ≥100 MB. We NEVER load the entire file into memory.
 * This module reads only the exact byte ranges needed, on demand:
 *
 * 1. Header:        File.slice(0, HEADER_SLICE_SIZE)          → parse_ld_header()
 * 2. Channel meta:  File.slice(0, metaEnd)                    → parse_ld_channels()
 * 3. Channel data:  File.slice(ch.dataOffset, ch.dataOffset + ch.dataByteLen) → WASM buffer
 *
 * No intermediate ArrayBuffer is kept after the Worker has consumed it.
 * All parsing and buffering happens inside the Worker thread.
 */

import type { ChannelInfo, ParseHeaderResponse } from './worker-protocol';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Bytes to read for the file header (covers all string fields, see ld_format_research.md §1). */
export const HEADER_SLICE_SIZE = 0x0200; // 512 B — conservative; actual used region < 0x200

// ---------------------------------------------------------------------------
// Slice helpers (browser File API)
// ---------------------------------------------------------------------------

/**
 * Read a byte range from a File as a Uint8Array.
 * Uses FileReader / arrayBuffer() on the slice — does NOT load the full file.
 */
export async function sliceFile(
  file: File,
  start: number,
  end: number,
): Promise<Uint8Array> {
  const blob = file.slice(start, end);
  const ab = await blob.arrayBuffer();
  return new Uint8Array(ab);
}

// ---------------------------------------------------------------------------
// Pipeline steps
// ---------------------------------------------------------------------------

/**
 * Step 1: Read the header region of the file.
 * Returns a Uint8Array of exactly HEADER_SLICE_SIZE bytes (or file end, whichever is smaller).
 */
export async function readHeaderSlice(file: File): Promise<Uint8Array> {
  return sliceFile(file, 0, Math.min(HEADER_SLICE_SIZE, file.size));
}

/**
 * Step 2: Read the channel meta region.
 *
 * We need bytes [0 .. channelMetaOffset + channelMetaSize] to traverse the linked list.
 * However, since channel_meta_size is only available after header parse, we compute:
 *   metaEnd = channelMetaOffset + channelMetaSize
 *
 * This is always << total file size and typically < 100 KB.
 */
export async function readMetaSlice(
  file: File,
  header: ParseHeaderResponse,
): Promise<Uint8Array> {
  // Estimate: we need from 0 up to at least channel_meta_offset + (max channels × 0x1A8).
  // Use data_offset as a safe upper bound (meta always precedes data).
  const metaEnd = Math.min(header.dataOffset, file.size);
  return sliceFile(file, 0, metaEnd);
}

/**
 * Step 3: Read the raw data slice for a single channel.
 *
 * Returns exactly `ch.dataByteLen` bytes starting at `ch.dataOffset`.
 * The caller passes this into `LOAD_CHANNEL_DATA` Worker request.
 *
 * This is the hot path — called once per channel, on demand (lazy).
 */
export async function readChannelDataSlice(
  file: File,
  ch: ChannelInfo,
): Promise<Uint8Array> {
  const start = ch.dataOffset;
  const end = start + ch.dataByteLen;
  if (end > file.size) {
    throw new RangeError(
      `Channel "${ch.name}": data range [${start}..${end}] exceeds file size ${file.size}`,
    );
  }
  return sliceFile(file, start, end);
}

// ---------------------------------------------------------------------------
// Full pipeline orchestrator
// ---------------------------------------------------------------------------

/**
 * Validates that a File looks like a valid .ld file before sending to Worker.
 *
 * Does NOT parse — only checks file size and reads the first 4 magic bytes
 * on the main thread to fail fast before dispatching a Worker job.
 */
export async function validateLdFileFast(file: File): Promise<void> {
  if (file.size < HEADER_SLICE_SIZE) {
    throw new Error(`File "${file.name}" is too small to be a valid .ld file (${file.size} bytes)`);
  }

  // Read just the 4-byte magic synchronously via a tiny slice.
  const magicBytes = await sliceFile(file, 0, 4);
  const magic =
    magicBytes[0] |
    (magicBytes[1] << 8) |
    (magicBytes[2] << 16) |
    (magicBytes[3] << 24);

  if (magic !== 0x0045_f836) {
    throw new Error(
      `File "${file.name}" is not a valid MoTeC .ld file (magic=0x${(magic >>> 0).toString(16).toUpperCase()})`,
    );
  }
}

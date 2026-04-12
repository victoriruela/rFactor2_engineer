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

/**
 * Bytes to scan for the LD header.
 *
 * Some telemetry loggers prepend metadata before the MoTeC header, so we scan a wider prefix
 * to avoid rejecting valid files with a non-zero header start offset.
 */
export const HEADER_SLICE_SIZE = 0x10000; // 64 KiB

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

  const header = await sliceFile(file, 0, HEADER_SLICE_SIZE);

  // ADL v0 format (rFactor2 native .ld): magic=0x00000040 at offset 0, version=0 at offset 4.
  // Check this first since it is an exact-offset match, not a scan.
  const v0Magic =
    (header[0] | (header[1] << 8) | (header[2] << 16) | (header[3] << 24)) >>> 0;
  const v0Version =
    (header[4] | (header[5] << 8) | (header[6] << 16) | (header[7] << 24)) >>> 0;
  if (v0Magic === 0x00000040 && v0Version === 0) {
    // Additional sanity check: channel_meta_offset at bytes[8..12] must be non-zero.
    const metaOff =
      (header[8] | (header[9] << 8) | (header[10] << 16) | (header[11] << 24)) >>> 0;
    if (metaOff > 0) {
      return; // Valid ADL v0 format.
    }
  }

  // LD3/LD4 format: scan for magic 0x0045F836 anywhere in the first HEADER_SLICE_SIZE bytes.
  let found = false;
  for (let i = 0; i + 3 < header.length; i += 1) {
    const magic =
      header[i] |
      (header[i + 1] << 8) |
      (header[i + 2] << 16) |
      (header[i + 3] << 24);
    if ((magic >>> 0) === 0x0045_f836) {
      found = true;
      break;
    }
  }

  if (!found) {
    const first4 =
      header[0] |
      (header[1] << 8) |
      (header[2] << 16) |
      (header[3] << 24);
    throw new Error(
      `File "${file.name}" no contiene cabecera LD válida (first_u32=0x${(first4 >>> 0).toString(16).toUpperCase()})`,
    );
  }
}

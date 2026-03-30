/**
 * MAS 2.90 Extractor — Extract .AIW files from rFactor2 .MAS archives.
 *
 * MAS 2.90 Format (rFactor2):
 *   Offset  0-15  : XOR-encoded header (magic: "GMOTOR_MAS_2.90\0")
 *   Offset 16-23  : Salt (8 bytes, used to derive TOC decryption key)
 *   Offset 24-143 : Padding (120 bytes, skipped)
 *   Offset 144-147: TOC block size (uint32 LE)
 *   Offset 148+   : TOC entries (each 256 bytes, XOR-encrypted)
 *   After TOC     : File data blocks (sequential, possibly zlib-compressed)
 *
 * Based on MAS2Extract (github.com/nlhans/MAS2Extract) MAS2Reader.cs.
 *
 * Usage:
 *   const aiwText = await extractAIWFromMAS(file);
 *   if (aiwText) { const waypoints = parseAIW(aiwText); }
 *
 * Dependencies: None (uses native browser APIs).
 *   - DecompressionStream('deflate') for zlib decompression (all modern browsers)
 *   - Falls back to pako.inflate() if DecompressionStream is unavailable
 *
 * @module mas_extractor
 */

// ── XOR Key Tables ──────────────────────────────────────────────────────

/**
 * FileTypeKeys — used to XOR-decode the 16-byte header.
 * Each byte is shifted right by 1 before XOR application.
 */
const FILE_TYPE_KEYS = [
  0xbb, 0x59, 0xd2, 0xfc, 0x2c, 0x80, 0x30, 0xe6,
  0x56, 0x4e, 0x79, 0x78, 0x77, 0xe3, 0x01, 0x5e,
];

/** Expected decoded magic string. */
const MAS_MAGIC = "GMOTOR_MAS_2.90\0";

// ── Key Derivation ──────────────────────────────────────────────────────

/**
 * Derive a 256-byte XOR key table from the 8-byte salt.
 *
 * The derivation rotates through salt bytes, modulated with position,
 * to produce a repeatable 256-byte key for TOC entry decryption.
 *
 * @param {Uint8Array} salt - 8-byte salt from the MAS header.
 * @returns {Uint8Array} 256-byte key table.
 */
function deriveFileHeaderKeys(salt) {
  const keys = new Uint8Array(256);
  for (let i = 0; i < 256; i++) {
    keys[i] = (salt[i % 8] + i * 7) & 0xff;
  }
  return keys;
}

// ── Header Decoding ─────────────────────────────────────────────────────

/**
 * Decode the 16-byte XOR-encoded MAS header.
 *
 * @param {Uint8Array} headerBytes - First 16 bytes of the MAS file.
 * @returns {string} Decoded header string.
 */
function decodeHeader(headerBytes) {
  const decoded = new Uint8Array(16);
  for (let i = 0; i < 16; i++) {
    decoded[i] = headerBytes[i] ^ (FILE_TYPE_KEYS[i] >> 1);
  }
  return new TextDecoder("utf-8").decode(decoded);
}

// ── TOC Entry Parsing ───────────────────────────────────────────────────

/**
 * Decrypt and parse a single 256-byte TOC entry.
 *
 * Entry layout (after decryption):
 *   Bytes   0-3  : file index (uint32 LE)
 *   Bytes  16-143: filename (128 bytes, null-terminated)
 *   Bytes 144-255: filepath (112 bytes, null-terminated)
 *   Bytes 248-251: uncompressed size (uint32 LE)
 *   Bytes 252-255: compressed size (uint32 LE)
 *
 * @param {Uint8Array} encrypted - 256-byte encrypted TOC entry.
 * @param {Uint8Array} keyTable  - 256-byte XOR key table.
 * @returns {{ filename: string, uncompressedSize: number, compressedSize: number }}
 */
function parseTOCEntry(encrypted, keyTable) {
  const decrypted = new Uint8Array(256);
  for (let i = 0; i < 256; i++) {
    decrypted[i] = encrypted[i] ^ keyTable[i];
  }

  const view = new DataView(decrypted.buffer, decrypted.byteOffset, 256);

  // Extract filename (bytes 16-143, null-terminated)
  const filenameBytes = decrypted.slice(16, 144);
  const nullIdx = filenameBytes.indexOf(0);
  const filename = new TextDecoder("utf-8").decode(
    filenameBytes.slice(0, nullIdx === -1 ? 128 : nullIdx)
  );

  const uncompressedSize = view.getUint32(248, true);
  const compressedSize = view.getUint32(252, true);

  return { filename, uncompressedSize, compressedSize };
}

// ── Decompression ───────────────────────────────────────────────────────

/**
 * Decompress zlib-compressed data using the native DecompressionStream API.
 * Falls back to pako.inflate() if DecompressionStream is unavailable.
 *
 * @param {Uint8Array} data - Compressed data.
 * @returns {Promise<Uint8Array>} Decompressed data.
 */
async function zlibDecompress(data) {
  // Try native DecompressionStream (available in Chrome 80+, Firefox 113+, Safari 16.4+)
  if (typeof DecompressionStream !== "undefined") {
    const ds = new DecompressionStream("deflate");
    const writer = ds.writable.getWriter();
    const reader = ds.readable.getReader();

    writer.write(data);
    writer.close();

    const chunks = [];
    let totalLength = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      totalLength += value.length;
    }

    const result = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
      result.set(chunk, offset);
      offset += chunk.length;
    }
    return result;
  }

  // Fallback: pako (must be loaded externally)
  if (typeof pako !== "undefined") {
    return pako.inflate(data);
  }

  throw new Error(
    "No decompression API available. " +
    "Use a browser with DecompressionStream support or include pako.js."
  );
}

// ── Main Extraction ─────────────────────────────────────────────────────

/**
 * Extract the first .AIW file from a rFactor2 .MAS archive.
 *
 * @param {File|Blob|ArrayBuffer} file - MAS archive (browser File from
 *   drag-and-drop / file input, Blob, or raw ArrayBuffer).
 * @returns {Promise<string|null>} AIW file content as UTF-8 text, or null
 *   if no .aiw file was found or the archive is invalid.
 */
async function extractAIWFromMAS(file) {
  let buffer;
  if (file instanceof ArrayBuffer) {
    buffer = file;
  } else if (typeof file.arrayBuffer === "function") {
    buffer = await file.arrayBuffer();
  } else {
    throw new TypeError("Expected a File, Blob, or ArrayBuffer");
  }

  const bytes = new Uint8Array(buffer);

  // ── 1. Verify header ─────────────────────────────────────────────────
  if (bytes.length < 148) {
    console.warn("[MAS] File too small to be a valid MAS archive.");
    return null;
  }

  const headerStr = decodeHeader(bytes.slice(0, 16));
  if (headerStr !== MAS_MAGIC) {
    console.warn(
      `[MAS] Invalid header. Expected "${MAS_MAGIC}", got "${headerStr}".`
    );
    // Fallback: try brute-force scan for .aiw pattern
    return fallbackScanForAIW(bytes);
  }

  // ── 2. Read salt (bytes 16-23) ────────────────────────────────────────
  const salt = bytes.slice(16, 24);

  // ── 3. Skip padding (120 bytes, offset 24-143) ───────────────────────

  // ── 4. Read TOC block size (bytes 144-147) ────────────────────────────
  const view = new DataView(buffer);
  const tocBlockSize = view.getUint32(144, true);

  if (tocBlockSize === 0 || tocBlockSize % 256 !== 0) {
    console.warn(`[MAS] Invalid TOC block size: ${tocBlockSize}`);
    return fallbackScanForAIW(bytes);
  }

  const numEntries = tocBlockSize / 256;
  const tocStart = 148;

  // ── 5. Derive key table from salt ─────────────────────────────────────
  const keyTable = deriveFileHeaderKeys(salt);

  // ── 6. Read and decrypt TOC entries ───────────────────────────────────
  const entries = [];
  for (let i = 0; i < numEntries; i++) {
    const offset = tocStart + i * 256;
    if (offset + 256 > bytes.length) {
      console.warn(`[MAS] TOC entry ${i} extends beyond file.`);
      break;
    }
    const encrypted = bytes.slice(offset, offset + 256);
    entries.push(parseTOCEntry(encrypted, keyTable));
  }

  // ── 7. Find the .AIW entry ────────────────────────────────────────────
  const dataStart = tocStart + tocBlockSize;
  let dataOffset = 0;

  for (const entry of entries) {
    if (entry.filename.toLowerCase().endsWith(".aiw")) {
      // ── 8. Read file data ─────────────────────────────────────────────
      const fileStart = dataStart + dataOffset;
      const fileEnd = fileStart + entry.compressedSize;

      if (fileEnd > bytes.length) {
        console.warn("[MAS] AIW data extends beyond file boundary.");
        return null;
      }

      let fileData = bytes.slice(fileStart, fileEnd);

      // ── 9. Decompress if needed ───────────────────────────────────────
      if (entry.compressedSize !== entry.uncompressedSize) {
        try {
          fileData = await zlibDecompress(fileData);
        } catch (err) {
          console.error("[MAS] Decompression failed:", err);
          return null;
        }
      }

      // ── 10. Decode as UTF-8 ───────────────────────────────────────────
      return new TextDecoder("utf-8").decode(fileData);
    }

    dataOffset += entry.compressedSize;
  }

  console.info("[MAS] No .aiw file found in archive TOC.");
  return null;
}

// ── Fallback: Brute-force scan ──────────────────────────────────────────

/**
 * Fallback extractor: scan raw bytes for .aiw filename pattern.
 *
 * This is used when the header doesn't match the expected MAS 2.90 magic,
 * which may happen with differently encrypted or versioned MAS files.
 *
 * NOTE: This is a best-effort heuristic. Full MAS 2.90 encrypted support
 * with non-standard key tables is a future enhancement.
 *
 * @param {Uint8Array} bytes - Raw file bytes.
 * @returns {string|null} Extracted AIW text, or null.
 */
function fallbackScanForAIW(bytes) {
  console.info("[MAS] Attempting fallback scan for .aiw pattern...");

  // Search for ".aiw" or ".AIW" as ASCII bytes in the file
  const patterns = [
    [0x2e, 0x61, 0x69, 0x77], // .aiw
    [0x2e, 0x41, 0x49, 0x57], // .AIW
  ];

  for (const pattern of patterns) {
    for (let i = 0; i < bytes.length - 4; i++) {
      if (
        bytes[i] === pattern[0] &&
        bytes[i + 1] === pattern[1] &&
        bytes[i + 2] === pattern[2] &&
        bytes[i + 3] === pattern[3]
      ) {
        // Found a match — look for "[Waypoint]" or "[waypoint]" after the TOC region
        // This is heuristic-based: scan forward from the match for AIW content markers
        const searchStart = Math.max(0, i - 256);
        const searchRegion = bytes.slice(searchStart, bytes.length);
        const text = new TextDecoder("utf-8", { fatal: false }).decode(searchRegion);

        const wpIdx = text.search(/\[Waypoint\]/i);
        if (wpIdx !== -1) {
          // Extract from the [Waypoint] marker to the end (or a reasonable limit)
          return text.slice(wpIdx);
        }
      }
    }
  }

  console.warn("[MAS] Fallback scan found no AIW content.");
  return null;
}

// ── Exports ─────────────────────────────────────────────────────────────

// ES module export (for bundlers and modern browsers)
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    extractAIWFromMAS,
    // Exposed for testing:
    decodeHeader,
    deriveFileHeaderKeys,
    parseTOCEntry,
    zlibDecompress,
    fallbackScanForAIW,
    FILE_TYPE_KEYS,
    MAS_MAGIC,
  };
}

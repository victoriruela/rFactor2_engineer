/**
 * Client-side extractor for rFactor2 .mas (archive) files.
 *
 * MAS files are a simple archive format used by rFactor2.
 * This extracts .aiw file content from inside a .mas archive.
 *
 * MAS v1 format (simplified):
 *   - Header: 4-byte magic "GMAS", then file table
 *   - Each entry has a null-terminated filename, offset, and size
 *   - We scan for .aiw filenames and extract the raw text content
 */

// eslint-disable-next-line no-unused-vars
function extractAIWFromMAS(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const textDecoder = new TextDecoder("utf-8", { fatal: false });

  // Strategy: scan for .aiw content by looking for known AIW markers
  // in the binary data. MAS files embed files with minimal framing.
  const fullText = textDecoder.decode(bytes);

  // Look for the AIW section - it contains [Waypoint] sections
  // Find the first occurrence of a waypoint pattern which signals AIW data
  const aiwMarkers = ["[Waypoint]", "pos=(", "trackName="];
  let aiwStart = -1;

  for (const marker of aiwMarkers) {
    const idx = fullText.indexOf(marker);
    if (idx !== -1 && (aiwStart === -1 || idx < aiwStart)) {
      aiwStart = idx;
    }
  }

  if (aiwStart === -1) {
    throw new Error("No AIW data found inside MAS archive");
  }

  // Walk backwards from the first marker to find start of the AIW section
  // Look for a header-like pattern or beginning of text data
  let searchStart = Math.max(0, aiwStart - 512);
  const headerPatterns = ["[Header]", "[Main]", "trackName"];
  for (const hp of headerPatterns) {
    const idx = fullText.indexOf(hp, searchStart);
    if (idx !== -1 && idx < aiwStart) {
      aiwStart = idx;
      break;
    }
  }

  // Extract from aiwStart to end of AIW data
  // AIW data ends when we hit binary garbage or another file boundary
  let aiwEnd = fullText.length;
  // Look for sequences of null bytes that indicate end of text section
  for (let i = aiwStart + 100; i < fullText.length - 4; i++) {
    const ch = fullText.charCodeAt(i);
    // If we find a long sequence of nulls, we've left the AIW section
    if (ch === 0 && fullText.charCodeAt(i + 1) === 0 &&
        fullText.charCodeAt(i + 2) === 0 && fullText.charCodeAt(i + 3) === 0) {
      aiwEnd = i;
      break;
    }
  }

  const aiwText = fullText.substring(aiwStart, aiwEnd);
  if (!aiwText.includes("pos=") && !aiwText.includes("pos =")) {
    throw new Error("Extracted data does not contain valid AIW waypoints");
  }

  return aiwText;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { extractAIWFromMAS };
}

/**
 * Client-side parser for rFactor2 .aiw (AI Waypoint) files.
 *
 * Extracts track centreline waypoints from raw AIW text.
 */

// eslint-disable-next-line no-unused-vars
function parseAIW(aiwText) {
  const waypointRe = /pos\s*=\s*\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)/gi;
  const trackNameRe = /^\s*trackName\s*=\s*(.+)/im;

  const nameMatch = trackNameRe.exec(aiwText);
  const trackName = nameMatch ? nameMatch[1].trim() : "Unknown";

  const points = [];
  let m;
  while ((m = waypointRe.exec(aiwText)) !== null) {
    points.push({
      x: parseFloat(m[1]),
      y: parseFloat(m[2]),
      z: parseFloat(m[3]),
    });
  }

  return {
    track_name: trackName,
    points: points,
    point_count: points.length,
  };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { parseAIW };
}

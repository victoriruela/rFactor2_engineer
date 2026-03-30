/**
 * Browser-side parser for rFactor2 .AIW (AI Waypoint) files.
 *
 * Coordinate mapping (same as Python backend):
 *   AIW: X=east, Y=up (elevation), Z=south
 *   Output: x=AIW_X, y=AIW_Z, z=AIW_Y  (z is always elevation)
 *
 * Usage:
 *   const text = await file.text();          // from <input type="file">
 *   const track = parseAIW(text, "Spa");
 *   // track.points[0] => {x, y, z, width_left, width_right}
 *
 * This file is a standalone reference implementation.  It will be
 * embedded inline in the Three.js component by tasks T5/T8.
 */

// eslint-disable-next-line no-unused-vars
function parseAIW(fileContent, trackName) {
  trackName = trackName || "Unknown";

  var floatPattern = "(-?\\d*\\.?\\d+)";
  var posRe = new RegExp(
    "wp_pos=\\(\\s*" +
      floatPattern + "\\s*,\\s*" +
      floatPattern + "\\s*,\\s*" +
      floatPattern + "\\s*\\)",
    "g"
  );
  var widthRe = new RegExp(
    "wp_width=\\(\\s*" +
      floatPattern + "\\s*,\\s*" +
      floatPattern + "\\s*,\\s*" +
      floatPattern + "\\s*,\\s*" +
      floatPattern + "\\s*\\)",
    "g"
  );

  var positions = [];
  var widths = [];
  var m;

  while ((m = posRe.exec(fileContent)) !== null) {
    positions.push({
      aiwX: parseFloat(m[1]),
      aiwY: parseFloat(m[2]),
      aiwZ: parseFloat(m[3]),
    });
  }

  while ((m = widthRe.exec(fileContent)) !== null) {
    widths.push({
      left: parseFloat(m[1]),
      right: parseFloat(m[2]),
    });
  }

  var points = positions.map(function (pos, i) {
    var w = widths[i] || { left: 0.0, right: 0.0 };
    return {
      x: pos.aiwX,
      y: pos.aiwZ,          // AIW_Z -> our y (horizontal)
      z: pos.aiwY,          // AIW_Y -> our z (elevation)
      width_left: w.left,
      width_right: w.right,
    };
  });

  return {
    name: trackName,
    source: "aiw",
    points: points,
  };
}

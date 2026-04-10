/**
 * Setup value parser for rFactor2 setup files (SVM format)
 * Format: "X//Y/Z" where:
 *   X = clicks / steps (integer)
 *   Y = numeric value
 *   Z = units (N/mm, °C, clicks, etc.)
 */

export interface ParsedSetupValue {
  clicks: string | null;      // The X part (e.g., "5")
  value: string;              // The Y part (e.g., "5")
  unit: string;               // The Z part (e.g., "clicks", "N/mm")
  full: string;               // Original unparsed value
  hasClicks: boolean;         // True if clicks/step info is present
}

/**
 * Parse a setup parameter value in format "X//Y/Z"
 * Examples:
 *   "5//clicks" → { clicks: "5", value: "5", unit: "clicks", hasClicks: true }
 *   "85000//N/mm" → { clicks: "85000", value: "85000", unit: "N/mm", hasClicks: true }
 *   "42" → { clicks: null, value: "42", unit: "", hasClicks: false }
 *   "3.5 mm" → { clicks: null, value: "3.5", unit: "mm", hasClicks: false }
 */
export function parseSetupValue(raw: string): ParsedSetupValue {
  const full = raw.trim();

  // Check for X//Y/Z format
  const doubleSlashIndex = full.indexOf('//');
  if (doubleSlashIndex >= 0) {
    // Format: X//Y or X//Y/Z
    const clicksStr = full.substring(0, doubleSlashIndex).trim();
    const rightPart = full.substring(doubleSlashIndex + 2).trim();

    // Try to parse right part as "Y/Z" or just "Z"
    const singleSlashIndex = rightPart.indexOf('/');
    let value: string;
    let unit: string;

    if (singleSlashIndex >= 0) {
      // Format: X//Y/Z
      value = rightPart.substring(0, singleSlashIndex).trim();
      unit = rightPart.substring(singleSlashIndex + 1).trim();
    } else {
      // Format: X//Y (where Y is numeric value + unit like "5 clicks" or "85000 N/mm")
      // Try to split by space to separate value and unit
      const parts = rightPart.split(/\s+/);
      if (parts.length >= 2) {
        value = parts[0];
        unit = parts.slice(1).join(' ');
      } else {
        // Entire right part is either value or unit; assume it's unit
        value = clicksStr; // Re-use clicks as value (fallback)
        unit = rightPart;
      }
    }

    return {
      clicks: clicksStr,
      value,
      unit,
      full,
      hasClicks: true,
    };
  }

  // Fallback: no double slash, try to split by space
  const parts = full.split(/\s+/);
  if (parts.length >= 2) {
    return {
      clicks: null,
      value: parts[0],
      unit: parts.slice(1).join(' '),
      full,
      hasClicks: false,
    };
  }

  // Single token (no unit)
  return {
    clicks: null,
    value: full,
    unit: '',
    full,
    hasClicks: false,
  };
}

/**
 * Returns the display string for clicks (#click column)
 * Returns the clicks value if present, otherwise a dash
 */
export function getClicksDisplay(raw: string): string {
  const parsed = parseSetupValue(raw);
  return parsed.clicks || '—';
}

/**
 * Returns the display string for the parameter value (without clicks prefix)
 * Examples:
 *   "5//clicks" → "5 clicks"
 *   "85000//N/mm" → "85000 N/mm"
 *   "42" → "42"
 */
export function getValueDisplay(raw: string): string {
  const parsed = parseSetupValue(raw);
  if (parsed.value && parsed.unit) {
    return `${parsed.value} ${parsed.unit}`;
  }
  return parsed.value || parsed.full;
}

/**
 * Infer total clicks for a parameter based on typical rFactor2 ranges
 * This is a heuristic; returns null if unable to infer
 * Common ranges:
 *   - ARBs: 0-19 clicks (spring / bump / rebound)
 *   - Ride height: 0-19 mm
 *   - Wing angles: 0-10 degrees
 */
export function inferTotalClicks(paramName: string, currentClicks: string | null): string | null {
  if (!currentClicks) {
    return null;
  }

  const param = paramName.toLowerCase();
  const click = parseInt(currentClicks, 10);

  // ARB stiffness (common in rF2)
  if (param.includes('arb') || param.includes('anti-roll')) {
    if (click >= 0 && click <= 19) {
      return '19 clicks';
    }
  }

  // Spring rates (when using "clicks" as a setting, typically 0-19 or 0-15)
  if (param.includes('spring') && currentClicks) {
    if (click >= 0 && click <= 19) {
      return '19 clicks';
    }
  }

  // Ride height (in mm, typically 0-20 mm range)
  if (param.includes('ride') || param.includes('height')) {
    if (click >= 0 && click <= 20) {
      return '20 mm';
    }
  }

  // Brake balance (0-100 in some cars)
  if (param.includes('brake') && param.includes('balance')) {
    if (click >= 0 && click <= 100) {
      return '100%';
    }
  }

  // Generic fallback: if it's a small integer, likely 0-19 range
  if (click >= 0 && click <= 19) {
    return '19 clicks';
  }

  return null;
}

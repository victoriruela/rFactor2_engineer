import init, * as LdParser from '../../wasm/ld_parser/pkg/ld_parser';
import { LD_PARSER_WASM_B64 } from '../../wasm/ld_parser/pkg/ld_parser_bg_inline';
import type {
  AnalysisResponse,
  LapStats,
  PreparsedAnalyzePayload,
  PreparsedSetup,
  SetupChange,
  TelemetrySample,
} from '../api';
import { readChannelDataSlice, readHeaderSlice, readMetaSlice, validateLdFileFast } from '../worker/file-slice-pipeline';

let wasmInitPromise: Promise<void> | null = null;

const ANALYSIS_MAX_SAMPLES = 12000;
const PREVIEW_MAX_SAMPLES = 60000;

function ensureWasmReady(): Promise<void> {
  if (!wasmInitPromise) {
    wasmInitPromise = (async () => {
      const binary = Uint8Array.from(atob(LD_PARSER_WASM_B64), (c) => c.charCodeAt(0));
      await init({ module_or_path: binary.buffer });
    })();
  }
  return wasmInitPromise;
}

function normalizeName(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function makeLookup(channels: Array<{ name: string; shortName: string; units: string; sampleRate: number; count: number; typeId: number; dataOffset: number; dataByteLen: number; shift: number; multiplier: number; scale: number; decimalPlaces: number }>) {
  const map = new Map<string, (typeof channels)[number]>();
  for (const ch of channels) {
    map.set(normalizeName(ch.name), ch);
    if (ch.shortName) {
      map.set(normalizeName(ch.shortName), ch);
    }
  }
  return map;
}

const CHANNEL_ALIASES: Record<string, string[]> = {
  Session_Elapsed_Time: ['Session_Elapsed_Time', 'Time', 'Time_s', 'SessionTime'],
  Lap_Number: ['Lap_Number', 'Lap', 'LapCount'],
  Speed: ['Speed', 'Ground_Speed', 'VehicleSpeed'],
  Throttle: ['Throttle', 'Throttle_Pos', 'ThrottlePos'],
  Brake: ['Brake', 'Brake_Pos', 'BrakePos'],
  RPM: ['RPM', 'Engine_RPM', 'EngineSpeed'],
  Gear: ['Gear'],
  Steering: ['Steering', 'Steering_Wheel_Position'],
  Steering_Torque: ['Steering_Shaft_Torque', 'Steer_Torque', 'SteeringTorque'],
  Clutch: ['Clutch', 'Clutch_Pos', 'ClutchPos'],
  G_Force_Lat: ['G_Force_Lat', 'LateralAcceleration', 'LatAccel'],
  G_Force_Long: ['G_Force_Long', 'LongitudinalAcceleration', 'LongAccel'],
  G_Force_Vert: ['G_Force_Vert', 'VerticalAcceleration', 'VertAccel'],
  GPS_Latitude: ['GPS Latitude', 'GPS_Latitude', 'GPS_Lat', 'Latitude'],
  GPS_Longitude: ['GPS Longitude', 'GPS_Longitude', 'GPS_Lon', 'Longitude'],
  Ride_Height_FL: ['Ride_Height_FL', 'Ride Height FL'],
  Ride_Height_FR: ['Ride_Height_FR', 'Ride Height FR'],
  Ride_Height_RL: ['Ride_Height_RL', 'Ride Height RL'],
  Ride_Height_RR: ['Ride_Height_RR', 'Ride Height RR'],
  Brake_Temp_FL: ['Brake_Temp_FL', 'Brake Temp FL'],
  Brake_Temp_FR: ['Brake_Temp_FR', 'Brake Temp FR'],
  Brake_Temp_RL: ['Brake_Temp_RL', 'Brake Temp RL'],
  Brake_Temp_RR: ['Brake_Temp_RR', 'Brake Temp RR'],
  Brake_Bias_Rear: ['Brake_Bias_Rear', 'Brake Bias Rear', 'BrakeBiasRear'],
  Tyre_Pressure_FL: ['Tyre_Pressure_FL', 'Tyre Pressure FL'],
  Tyre_Pressure_FR: ['Tyre_Pressure_FR', 'Tyre Pressure FR'],
  Tyre_Pressure_RL: ['Tyre_Pressure_RL', 'Tyre Pressure RL'],
  Tyre_Pressure_RR: ['Tyre_Pressure_RR', 'Tyre Pressure RR'],
  Tyre_Temp_FL_Centre: ['Tyre_Temp_FL_Centre', 'Tyre Temp FL Centre'],
  Tyre_Temp_FR_Centre: ['Tyre_Temp_FR_Centre', 'Tyre Temp FR Centre'],
  Tyre_Temp_RL_Centre: ['Tyre_Temp_RL_Centre', 'Tyre Temp RL Centre'],
  Tyre_Temp_RR_Centre: ['Tyre_Temp_RR_Centre', 'Tyre Temp RR Centre'],
  Tyre_Temp_FL_Inner: ['Tyre_Temp_FL_Inner', 'Tyre Temp FL Inner'],
  Tyre_Temp_FL_Outer: ['Tyre_Temp_FL_Outer', 'Tyre Temp FL Outer'],
  Tyre_Temp_FR_Inner: ['Tyre_Temp_FR_Inner', 'Tyre Temp FR Inner'],
  Tyre_Temp_FR_Outer: ['Tyre_Temp_FR_Outer', 'Tyre Temp FR Outer'],
  Tyre_Temp_RL_Inner: ['Tyre_Temp_RL_Inner', 'Tyre Temp RL Inner'],
  Tyre_Temp_RL_Outer: ['Tyre_Temp_RL_Outer', 'Tyre Temp RL Outer'],
  Tyre_Temp_RR_Inner: ['Tyre_Temp_RR_Inner', 'Tyre Temp RR Inner'],
  Tyre_Temp_RR_Outer: ['Tyre_Temp_RR_Outer', 'Tyre Temp RR Outer'],
  Tyre_Wear_FL: ['Tyre_Wear_FL', 'Tyre Wear FL'],
  Tyre_Wear_FR: ['Tyre_Wear_FR', 'Tyre Wear FR'],
  Tyre_Wear_RL: ['Tyre_Wear_RL', 'Tyre Wear RL'],
  Tyre_Wear_RR: ['Tyre_Wear_RR', 'Tyre Wear RR'],
  Tyre_Load_FL: ['Tyre_Load_FL', 'Tyre Load FL'],
  Tyre_Load_FR: ['Tyre_Load_FR', 'Tyre Load FR'],
  Tyre_Load_RL: ['Tyre_Load_RL', 'Tyre Load RL'],
  Tyre_Load_RR: ['Tyre_Load_RR', 'Tyre Load RR'],
  Grip_Fract_FL: ['Grip_Fract_FL', 'Grip Fract FL'],
  Grip_Fract_FR: ['Grip_Fract_FR', 'Grip Fract FR'],
  Grip_Fract_RL: ['Grip_Fract_RL', 'Grip Fract RL'],
  Grip_Fract_RR: ['Grip_Fract_RR', 'Grip Fract RR'],
  Wheel_Rot_Speed_FL: ['Wheel_Rot_Speed_FL', 'Wheel Rot Speed FL'],
  Wheel_Rot_Speed_FR: ['Wheel_Rot_Speed_FR', 'Wheel Rot Speed FR'],
  Wheel_Rot_Speed_RL: ['Wheel_Rot_Speed_RL', 'Wheel Rot Speed RL'],
  Wheel_Rot_Speed_RR: ['Wheel_Rot_Speed_RR', 'Wheel Rot Speed RR'],
  Eng_Oil_Temp: ['Eng_Oil_Temp', 'Eng Oil Temp', 'OilTemp'],
  Eng_Water_Temp: ['Eng_Water_Temp', 'Eng Water Temp', 'WaterTemp'],
  Fuel_Level: ['Fuel_Level', 'Fuel Level', 'FuelLevel'],
};

function decodeSample(view: DataView, typeId: number, offset: number): number {
  switch (typeId) {
    case 0x0000:
      return view.getFloat32(offset, true);
    case 0x0001:
      return view.getInt16(offset, true);
    case 0x0002:
      return view.getInt16(offset, true);
    case 0x0003:
      return view.getUint32(offset, true);
    case 0x0004:
      return view.getInt32(offset, true);
    case 0x0007:
      return view.getFloat64(offset, true);
    case 0x0008:
      return view.getInt8(offset);
    default:
      return 0;
  }
}

/**
 * Apply ADL v0 physical scaling formula to a raw sample value.
 * Formula: physical = raw * multiplier / (scale * 10^decimalPlaces) + shift
 * The shift is a physical-domain offset (not a raw-domain offset).
 * For Float32/Float64 channels (pre-scaled), returns raw unchanged.
 */
function applyScaling(
  raw: number,
  typeId: number,
  shift: number,
  multiplier: number,
  scale: number,
  decimalPlaces: number,
): number {
  // Float channels are already physical values — no scaling needed.
  if (typeId === 0x0000 || typeId === 0x0007) return raw;
  // If scaling fields look identity-like, return raw.
  if (multiplier === 1 && scale === 1 && decimalPlaces === 0 && shift === 0) return raw;
  const s = scale !== 0 ? scale : 1;
  return raw * multiplier / (s * Math.pow(10, decimalPlaces)) + shift;
}

function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(a)));
}

function deriveCircuitNameFromFilename(filename: string): string {
  const cleaned = filename
    .replace(/\.(ld|mat|csv)$/i, '')
    .replace(/^\d{4}-\d{2}-\d{2}\s*-\s*\d{2}-\d{2}-\d{2}\s*-\s*/i, '')
    .replace(/^\d{8,}\s*-\s*/i, '')
    .replace(/\s*-\s*(R|Q|FP|P)\d+$/i, '')
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned || 'Desconocido';
}

function sampleIndices(count: number, target: number): number[] {
  const n = Math.max(1, count);
  const m = Math.max(1, Math.min(target, n));
  const idx: number[] = new Array(m);
  for (let i = 0; i < m; i += 1) {
    idx[i] = m === 1 ? 0 : Math.floor((i * (n - 1)) / (m - 1));
  }
  return idx;
}

function downsampleSeries(values: number[], targetCount: number): number[] {
  if (values.length <= targetCount) return values;
  const idx = sampleIndices(values.length, targetCount);
  const out = new Array<number>(idx.length);
  for (let i = 0; i < idx.length; i += 1) {
    out[i] = values[idx[i]];
  }
  return out;
}

function resampleSeriesToCount(values: number[], targetCount: number): number[] {
  if (targetCount <= 0) return [];
  if (values.length === 0) return new Array<number>(targetCount).fill(0);
  if (values.length === targetCount) return values;
  if (targetCount === 1) return [values[0]];

  const out = new Array<number>(targetCount);
  for (let i = 0; i < targetCount; i += 1) {
    const position = (i / (targetCount - 1)) * (values.length - 1);
    const left = Math.floor(position);
    const right = Math.min(values.length - 1, Math.ceil(position));
    if (left === right) {
      out[i] = values[left];
      continue;
    }
    const ratio = position - left;
    out[i] = values[left] + (values[right] - values[left]) * ratio;
  }
  return out;
}

function alignChannelsToCount(channels: Record<string, number[]>, targetCount: number): Record<string, number[]> {
  const out: Record<string, number[]> = {};
  for (const [key, values] of Object.entries(channels)) {
    out[key] = resampleSeriesToCount(values, targetCount);
  }
  return out;
}

function downsampleChannels(channels: Record<string, number[]>, targetCount: number): Record<string, number[]> {
  const out: Record<string, number[]> = {};
  for (const [key, values] of Object.entries(channels)) {
    out[key] = downsampleSeries(values, targetCount);
  }
  return out;
}

async function readChannelSampled(
  file: File,
  ch: {
    name: string;
    shortName: string;
    units: string;
    sampleRate: number;
    count: number;
    typeId: number;
    dataOffset: number;
    dataByteLen: number;
    shift: number;
    multiplier: number;
    scale: number;
    decimalPlaces: number;
  },
  targetCount: number,
): Promise<number[]> {
  const bytes = await readChannelDataSlice(file, ch);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const sampleSize = LdParser.sample_byte_size(ch.typeId);
  if (sampleSize <= 0) {
    return [];
  }

  const idx = sampleIndices(ch.count, targetCount);
  const out = new Array<number>(idx.length);
  for (let i = 0; i < idx.length; i += 1) {
    const byteOffset = idx[i] * sampleSize;
    const raw = decodeSample(view, ch.typeId, byteOffset);
    out[i] = applyScaling(raw, ch.typeId, ch.shift, ch.multiplier, ch.scale, ch.decimalPlaces);
  }
  return out;
}

function safeArray(channels: Record<string, number[]>, key: string): number[] {
  return Array.isArray(channels[key]) ? channels[key] : [];
}

function getAt(arr: number[], i: number): number {
  if (i >= 0 && i < arr.length) return arr[i];
  return 0;
}

function buildTelemetrySeries(channels: Record<string, number[]>): TelemetrySample[] {
  const t = safeArray(channels, 'Session_Elapsed_Time');
  const lap = safeArray(channels, 'Lap_Number');
  const spd = safeArray(channels, 'Speed');
  const thr = safeArray(channels, 'Throttle');
  const brk = safeArray(channels, 'Brake');
  const rpm = safeArray(channels, 'RPM');
  const gear = safeArray(channels, 'Gear');
  const steer = safeArray(channels, 'Steering');
  const steerTorque = safeArray(channels, 'Steering_Torque');
  const clutch = safeArray(channels, 'Clutch');
  const gLat = safeArray(channels, 'G_Force_Lat');
  const gLong = safeArray(channels, 'G_Force_Long');
  const gVert = safeArray(channels, 'G_Force_Vert');
  const lat = safeArray(channels, 'GPS_Latitude');
  const lon = safeArray(channels, 'GPS_Longitude');
  const rideHFL = safeArray(channels, 'Ride_Height_FL');
  const rideHFR = safeArray(channels, 'Ride_Height_FR');
  const rideHRL = safeArray(channels, 'Ride_Height_RL');
  const rideHRR = safeArray(channels, 'Ride_Height_RR');
  const brakeTFL = safeArray(channels, 'Brake_Temp_FL');
  const brakeTFR = safeArray(channels, 'Brake_Temp_FR');
  const brakeTRL = safeArray(channels, 'Brake_Temp_RL');
  const brakeTRR = safeArray(channels, 'Brake_Temp_RR');
  const brakeBias = safeArray(channels, 'Brake_Bias_Rear');
  const tyrePFL = safeArray(channels, 'Tyre_Pressure_FL');
  const tyrePFR = safeArray(channels, 'Tyre_Pressure_FR');
  const tyrePRL = safeArray(channels, 'Tyre_Pressure_RL');
  const tyrePRR = safeArray(channels, 'Tyre_Pressure_RR');
  const tyreTFL = safeArray(channels, 'Tyre_Temp_FL_Centre');
  const tyreTFR = safeArray(channels, 'Tyre_Temp_FR_Centre');
  const tyreTRL = safeArray(channels, 'Tyre_Temp_RL_Centre');
  const tyreTRR = safeArray(channels, 'Tyre_Temp_RR_Centre');
  const tyreTFLInner = safeArray(channels, 'Tyre_Temp_FL_Inner');
  const tyreTFLOuter = safeArray(channels, 'Tyre_Temp_FL_Outer');
  const tyreTFRInner = safeArray(channels, 'Tyre_Temp_FR_Inner');
  const tyreTFROuter = safeArray(channels, 'Tyre_Temp_FR_Outer');
  const tyreTRLInner = safeArray(channels, 'Tyre_Temp_RL_Inner');
  const tyreTRLOuter = safeArray(channels, 'Tyre_Temp_RL_Outer');
  const tyreTRRInner = safeArray(channels, 'Tyre_Temp_RR_Inner');
  const tyreTRROuter = safeArray(channels, 'Tyre_Temp_RR_Outer');
  const tyreWFL = safeArray(channels, 'Tyre_Wear_FL');
  const tyreWFR = safeArray(channels, 'Tyre_Wear_FR');
  const tyreWRL = safeArray(channels, 'Tyre_Wear_RL');
  const tyreWRR = safeArray(channels, 'Tyre_Wear_RR');
  const tyreLFL = safeArray(channels, 'Tyre_Load_FL');
  const tyreLFR = safeArray(channels, 'Tyre_Load_FR');
  const tyreLRL = safeArray(channels, 'Tyre_Load_RL');
  const tyreLRR = safeArray(channels, 'Tyre_Load_RR');
  const gripFL = safeArray(channels, 'Grip_Fract_FL');
  const gripFR = safeArray(channels, 'Grip_Fract_FR');
  const gripRL = safeArray(channels, 'Grip_Fract_RL');
  const gripRR = safeArray(channels, 'Grip_Fract_RR');
  const wheelSpFL = safeArray(channels, 'Wheel_Rot_Speed_FL');
  const wheelSpFR = safeArray(channels, 'Wheel_Rot_Speed_FR');
  const wheelSpRL = safeArray(channels, 'Wheel_Rot_Speed_RL');
  const wheelSpRR = safeArray(channels, 'Wheel_Rot_Speed_RR');
  const oilTemp = safeArray(channels, 'Eng_Oil_Temp');
  const waterTemp = safeArray(channels, 'Eng_Water_Temp');
  const fuelLevel = safeArray(channels, 'Fuel_Level');

  const n = t.length;
  // Linearly interpolate time for sub-second precision.
  // The raw Session_Elapsed_Time channel has integer-second values (dec=0).
  // Interpolating between first/last gives smooth fractional-second timestamps.
  const tFirst = t.length > 0 ? t[0] : 0;
  const tLast = t.length > 1 ? t[t.length - 1] : tFirst;
  const tSpan = tLast - tFirst;
  const useInterp = n > 1 && tSpan > 0;

  const out: TelemetrySample[] = new Array(n);
  for (let i = 0; i < n; i += 1) {
    const tInterp = useInterp ? tFirst + (i / (n - 1)) * tSpan : getAt(t, i);
    out[i] = {
      t: tInterp,
      spd: getAt(spd, i),
      thr: getAt(thr, i),
      brk: getAt(brk, i),
      rpm: getAt(rpm, i),
      gear: Math.round(getAt(gear, i)),
      lat: getAt(lat, i),
      lon: getAt(lon, i),
      lap: Math.round(getAt(lap, i)),
      steer: getAt(steer, i),
      steer_torque: getAt(steerTorque, i),
      clutch: getAt(clutch, i),
      g_lat: getAt(gLat, i),
      g_long: getAt(gLong, i),
      g_vert: getAt(gVert, i),
      ride_h_fl: getAt(rideHFL, i),
      ride_h_fr: getAt(rideHFR, i),
      ride_h_rl: getAt(rideHRL, i),
      ride_h_rr: getAt(rideHRR, i),
      brake_t_fl: getAt(brakeTFL, i),
      brake_t_fr: getAt(brakeTFR, i),
      brake_t_rl: getAt(brakeTRL, i),
      brake_t_rr: getAt(brakeTRR, i),
      brake_bias: getAt(brakeBias, i),
      tyre_p_fl: getAt(tyrePFL, i),
      tyre_p_fr: getAt(tyrePFR, i),
      tyre_p_rl: getAt(tyrePRL, i),
      tyre_p_rr: getAt(tyrePRR, i),
      tyre_t_fl: getAt(tyreTFL, i),
      tyre_t_fr: getAt(tyreTFR, i),
      tyre_t_rl: getAt(tyreTRL, i),
      tyre_t_rr: getAt(tyreTRR, i),
      tyre_t_fl_inner: getAt(tyreTFLInner, i),
      tyre_t_fl_outer: getAt(tyreTFLOuter, i),
      tyre_t_fr_inner: getAt(tyreTFRInner, i),
      tyre_t_fr_outer: getAt(tyreTFROuter, i),
      tyre_t_rl_inner: getAt(tyreTRLInner, i),
      tyre_t_rl_outer: getAt(tyreTRLOuter, i),
      tyre_t_rr_inner: getAt(tyreTRRInner, i),
      tyre_t_rr_outer: getAt(tyreTRROuter, i),
      tyre_w_fl: getAt(tyreWFL, i),
      tyre_w_fr: getAt(tyreWFR, i),
      tyre_w_rl: getAt(tyreWRL, i),
      tyre_w_rr: getAt(tyreWRR, i),
      tyre_l_fl: getAt(tyreLFL, i),
      tyre_l_fr: getAt(tyreLFR, i),
      tyre_l_rl: getAt(tyreLRL, i),
      tyre_l_rr: getAt(tyreLRR, i),
      grip_fl: getAt(gripFL, i),
      grip_fr: getAt(gripFR, i),
      grip_rl: getAt(gripRL, i),
      grip_rr: getAt(gripRR, i),
      wheel_sp_fl: getAt(wheelSpFL, i),
      wheel_sp_fr: getAt(wheelSpFR, i),
      wheel_sp_rl: getAt(wheelSpRL, i),
      wheel_sp_rr: getAt(wheelSpRR, i),
      oil_temp: getAt(oilTemp, i),
      water_temp: getAt(waterTemp, i),
      fuel_level: getAt(fuelLevel, i),
    };
  }
  return out;
}

/**
 * GPS projection-based interpolation for sub-sample S/F line crossing.
 *
 * 1. Estimate the S/F line position by averaging GPS coordinates at the
 *    first few lap-channel transitions.
 * 2. For each transition, project the S/F point onto consecutive GPS
 *    segments and pick the segment with the smallest perpendicular
 *    distance whose projection parameter t ∈ [0, 1].
 * 3. The crossing fraction within the GPS sample interval equals t.
 *
 * The projection method is geometrically exact (linear segments) and
 * avoids the non-linear bias of haversine distance-ratio interpolation,
 * yielding sub-millisecond consistency with MoTeC i2 Pro for most laps.
 */
function buildGpsInterpolatedDurations(
  lapSeries: number[],
  lapSampleRate: number,
  gps: { lat: number[]; lon: number[]; sampleRate: number },
): Map<number, number> {
  const durations = new Map<number, number>();
  const n = lapSeries.length;

  // Collect lap-channel transitions (at lapSampleRate Hz)
  interface Transition { idx: number; fromLap: number; toLap: number }
  const transitions: Transition[] = [];
  let prevLap: number | null = null;
  for (let i = 0; i < n; i += 1) {
    const lap = Math.round(lapSeries[i]);
    // Allow the 0→1 transition (race start) so lap 1 gets a GPS-precise crossing time.
    if (prevLap !== null && prevLap !== lap && lap > 0) {
      transitions.push({ idx: i, fromLap: prevLap, toLap: lap });
    }
    prevLap = lap;
  }
  if (transitions.length < 2) return durations;

  // Estimate S/F line coordinates from the first few transitions
  const calibCount = Math.min(14, transitions.length);
  let sfLat = 0;
  let sfLon = 0;
  let sfN = 0;
  for (let ti = 0; ti < calibCount; ti += 1) {
    const gpsIdx = Math.round(transitions[ti].idx * gps.sampleRate / lapSampleRate);
    if (gpsIdx < 0 || gpsIdx >= gps.lat.length) continue;
    const la = gps.lat[gpsIdx];
    const lo = gps.lon[gpsIdx];
    if (!Number.isFinite(la) || !Number.isFinite(lo)) continue;
    if (Math.abs(la) < 1e-6 && Math.abs(lo) < 1e-6) continue;
    sfLat += la;
    sfLon += lo;
    sfN += 1;
  }
  if (sfN === 0) return durations;
  sfLat /= sfN;
  sfLon /= sfN;

  // Convert S/F to local metres for projection (flat-earth approximation,
  // valid for the ~30 m distances we deal with around S/F).
  const DEG_TO_M_LAT = 111_320;
  const DEG_TO_M_LON = 111_320 * Math.cos((sfLat * Math.PI) / 180);

  // For each transition, find the GPS segment whose projection of the
  // S/F point yields the smallest perpendicular distance with t ∈ [0,1].
  const crossingTimes = new Map<number, number>();
  for (const tr of transitions) {
    const trTimeSec = tr.idx / lapSampleRate;
    const gpsCenterIdx = Math.round(trTimeSec * gps.sampleRate);
    const searchRadius = 4; // ±4 GPS samples

    let bestJ = -1;
    let bestT = 0;
    let bestPerp = Infinity;

    for (let j = gpsCenterIdx - searchRadius; j < gpsCenterIdx + searchRadius; j += 1) {
      if (j < 0 || j + 1 >= gps.lat.length) continue;
      const lat1 = gps.lat[j];
      const lon1 = gps.lon[j];
      const lat2 = gps.lat[j + 1];
      const lon2 = gps.lon[j + 1];
      if (!Number.isFinite(lat1) || !Number.isFinite(lon1)) continue;
      if (!Number.isFinite(lat2) || !Number.isFinite(lon2)) continue;

      // Convert to local metre offsets relative to S/F
      const x1 = (lon1 - sfLon) * DEG_TO_M_LON;
      const y1 = (lat1 - sfLat) * DEG_TO_M_LAT;
      const x2 = (lon2 - sfLon) * DEG_TO_M_LON;
      const y2 = (lat2 - sfLat) * DEG_TO_M_LAT;

      // S/F in this frame is (0, 0). Project onto segment P1→P2.
      const dx = x2 - x1;
      const dy = y2 - y1;
      const segLenSq = dx * dx + dy * dy;
      if (segLenSq < 1e-12) continue; // degenerate segment

      // t = dot(SF - P1, P2 - P1) / |P2 - P1|²
      // SF = (0,0), so SF - P1 = (-x1, -y1)
      const t = (-x1 * dx + -y1 * dy) / segLenSq;
      const tClamped = Math.max(0, Math.min(1, t));
      // Perpendicular distance at projected point
      const px = x1 + tClamped * dx;
      const py = y1 + tClamped * dy;
      const perpDist = Math.sqrt(px * px + py * py);

      // Prefer segments where the projection falls inside [0,1]
      // and the perpendicular distance is smallest.
      if (t >= -0.1 && t <= 1.1 && perpDist < bestPerp) {
        bestJ = j;
        bestT = Math.max(0, Math.min(1, t));
        bestPerp = perpDist;
      }
    }

    if (bestJ < 0 || bestPerp > 100) continue; // 100 m sanity bound
    const crossingTime = (bestJ + bestT) / gps.sampleRate;
    crossingTimes.set(tr.toLap, crossingTime);
  }

  // Convert crossing times to lap durations
  const laps = [...crossingTimes.keys()].sort((a, b) => a - b);
  for (const lap of laps) {
    const start = crossingTimes.get(lap)!;
    const end = crossingTimes.get(lap + 1);
    if (end == null) continue;
    const dur = end - start;
    if (dur > 0) durations.set(lap, dur);
  }

  return durations;
}

function buildPreciseLapDurations(
  timeSeries: number[],
  lapSeries: number[],
  sampleRateHz: number,
  gpsSeries?: { lat: number[]; lon: number[]; sampleRate: number },
): Map<number, number> {
  // ── GPS-interpolated timing (ms precision) ──────────────────────
  // Find lap boundaries from the full-res lap channel, then for each
  // boundary use GPS distance-ratio interpolation to pin-point the
  // exact S/F line crossing between two GPS samples.
  if (gpsSeries && gpsSeries.lat.length > 10 && gpsSeries.lon.length > 10) {
    const gpsDurations = buildGpsInterpolatedDurations(lapSeries, sampleRateHz, gpsSeries);
    if (gpsDurations.size > 0) return gpsDurations;
  }

  // ── Fallback: sample-index based (20 ms quantum at 50 Hz) ──────
  const n = Math.min(timeSeries.length, lapSeries.length);
  const useSampleRate = Number.isFinite(sampleRateHz) && sampleRateHz > 0;

  const sampleStartIdx = new Map<number, number>();
  const sampleEndIdx = new Map<number, number>();
  const sampleStartTime = new Map<number, number>();
  const sampleEndTime = new Map<number, number>();
  const startBoundaryIdx = new Map<number, number>();
  const endBoundaryIdx = new Map<number, number>();
  const startBoundaryTime = new Map<number, number>();
  const endBoundaryTime = new Map<number, number>();

  for (let i = 0; i < n; i += 1) {
    const lap = Math.round(lapSeries[i]);
    const t = timeSeries[i];
    if (!Number.isFinite(lap) || lap <= 0) continue;
    if (!sampleStartIdx.has(lap)) sampleStartIdx.set(lap, i);
    sampleEndIdx.set(lap, i);
    if (Number.isFinite(t)) {
      if (!sampleStartTime.has(lap)) sampleStartTime.set(lap, t);
      sampleEndTime.set(lap, t);
    }
  }

  for (let i = 1; i < n; i += 1) {
    const prevLap = Math.round(lapSeries[i - 1]);
    const currLap = Math.round(lapSeries[i]);
    if (!Number.isFinite(prevLap) || !Number.isFinite(currLap)) continue;
    if (prevLap <= 0 || currLap <= 0 || prevLap === currLap) continue;

    const boundaryIdx = i - 0.5;
    endBoundaryIdx.set(prevLap, boundaryIdx);
    if (!startBoundaryIdx.has(currLap)) startBoundaryIdx.set(currLap, boundaryIdx);

    const prevT = timeSeries[i - 1];
    const currT = timeSeries[i];
    if (Number.isFinite(prevT) && Number.isFinite(currT)) {
      const boundaryTime = prevT <= currT ? (prevT + currT) / 2 : currT;
      endBoundaryTime.set(prevLap, boundaryTime);
      if (!startBoundaryTime.has(currLap)) startBoundaryTime.set(currLap, boundaryTime);
    }
  }

  const durations = new Map<number, number>();
  for (const [lap, startIdx] of sampleStartIdx.entries()) {
    const endIdx = sampleEndIdx.get(lap);
    if (!Number.isFinite(endIdx)) continue;

    if (useSampleRate) {
      const start = startBoundaryIdx.get(lap) ?? startIdx;
      const end = endBoundaryIdx.get(lap) ?? (endIdx as number);
      const duration = Math.max(0, (end - start) / sampleRateHz);
      if (duration > 0) durations.set(lap, duration);
      continue;
    }

    const startTime = sampleStartTime.get(lap);
    const endTime = sampleEndTime.get(lap);
    if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) continue;
    const start = startBoundaryTime.get(lap) ?? (startTime as number);
    const end = endBoundaryTime.get(lap) ?? (endTime as number);
    const duration = Math.max(0, end - start);
    if (duration > 0) durations.set(lap, duration);
  }

  return durations;
}

function buildLapStats(series: TelemetrySample[], preciseDurations?: Map<number, number>): LapStats[] {
  const byLap = new Map<number, TelemetrySample[]>();
  for (const s of series) {
    // Include lap 0: in rFactor2 race sessions lap 0 is the formation/out-lap.
    // filterDisplayLaps removes only the last lap (inlap); lap 0 is kept.
    if (!Number.isFinite(s.lap) || s.lap < 0) continue;
    const lap = Math.round(s.lap);
    const arr = byLap.get(lap) ?? [];
    arr.push(s);
    byLap.set(lap, arr);
  }

  const laps: LapStats[] = [];
  for (const [lap, arr] of byLap) {
    if (arr.length < 2) continue;
    const sampledDuration = Math.max(0, arr[arr.length - 1].t - arr[0].t);
    const duration = preciseDurations?.get(lap) ?? sampledDuration;
    const avgSpeed = arr.reduce((a, s) => a + s.spd, 0) / arr.length;
    const maxSpeed = arr.reduce((m, s) => Math.max(m, s.spd), 0);
    const avgThrottle = arr.reduce((a, s) => a + s.thr, 0) / arr.length;
    const avgBrake = arr.reduce((a, s) => a + s.brk, 0) / arr.length;
    const avgRpm = arr.reduce((a, s) => a + s.rpm, 0) / arr.length;

    // Tyre wear delta per lap = max − min across all samples in the lap.
    // Using max-min avoids bias from noise in first/last samples.
    const wearDelta = (key: 'tyre_w_fl' | 'tyre_w_fr' | 'tyre_w_rl' | 'tyre_w_rr'): number | undefined => {
      const vals = arr.map((s) => s[key]).filter((v) => Number.isFinite(v));
      if (vals.length === 0) return undefined;
      const maxW = Math.max(...vals);
      const minW = Math.min(...vals);
      const delta = maxW - minW;
      return delta >= 0 ? delta : undefined;
    };

    // Fuel consumed (first sample minus last sample in the lap)
    const fuelFirst = arr[0].fuel_level;
    const fuelLast = arr[arr.length - 1].fuel_level;
    const fuelUsed = Number.isFinite(fuelFirst) && Number.isFinite(fuelLast) && fuelFirst > fuelLast
      ? fuelFirst - fuelLast
      : undefined;

    laps.push({
      lap,
      duration,
      avg_speed: avgSpeed,
      max_speed: maxSpeed,
      avg_throttle: avgThrottle,
      max_throttle: arr.reduce((m, s) => Math.max(m, s.thr), 0),
      avg_brake: avgBrake,
      max_brake: arr.reduce((m, s) => Math.max(m, s.brk), 0),
      avg_rpm: avgRpm,
      wear_fl: wearDelta('tyre_w_fl'),
      wear_fr: wearDelta('tyre_w_fr'),
      wear_rl: wearDelta('tyre_w_rl'),
      wear_rr: wearDelta('tyre_w_rr'),
      fuel_used: fuelUsed,
    });
  }

  laps.sort((a, b) => a.lap - b.lap);
  return laps;
}

function buildLapDistances(series: TelemetrySample[]): Map<number, number> {
  const byLap = new Map<number, TelemetrySample[]>();
  for (const s of series) {
    const lap = Math.round(s.lap);
    if (!Number.isFinite(lap) || lap < 0) continue;
    const arr = byLap.get(lap) ?? [];
    arr.push(s);
    byLap.set(lap, arr);
  }

  const distances = new Map<number, number>();
  for (const [lap, arr] of byLap.entries()) {
    if (arr.length < 2) continue;
    let total = 0;
    let prev: TelemetrySample | null = null;
    for (const sample of arr) {
      const valid = Number.isFinite(sample.lat)
        && Number.isFinite(sample.lon)
        && sample.lat >= -90
        && sample.lat <= 90
        && sample.lon >= -180
        && sample.lon <= 180
        && (Math.abs(sample.lat) > 1e-6 || Math.abs(sample.lon) > 1e-6);
      if (!valid) continue;
      if (prev) {
        total += haversineMeters(prev.lat, prev.lon, sample.lat, sample.lon);
      }
      prev = sample;
    }
    if (total > 0) distances.set(lap, total);
  }
  return distances;
}

function filterDisplayLaps(laps: LapStats[], _lapDistances?: Map<number, number>): LapStats[] {
  const sorted = laps
    .filter((lap) => Number.isFinite(lap.lap) && lap.lap >= 0 && Number.isFinite(lap.duration) && lap.duration > 0)
    .sort((a, b) => a.lap - b.lap);

  if (sorted.length === 0) return sorted;

  // Remove lap 0 (formation/outlap) if present — race sessions in rFactor2 start with a
  // formation lap recorded as lap 0. Practice sessions don't have it, so we keep from [0].
  const withoutFormation = sorted[0].lap === 0 ? sorted.slice(1) : sorted;

  // Remove the last entry (inlap / incomplete lap).
  return withoutFormation.length > 1 ? withoutFormation.slice(0, -1) : withoutFormation;
}

export async function parseLdToPreparsedTelemetry(
  file: File,
  analysisMaxSamples = ANALYSIS_MAX_SAMPLES,
  previewMaxSamples = PREVIEW_MAX_SAMPLES,
): Promise<{
  channels: Record<string, number[]>;
  timeCol: string;
  lapCol: string;
  preview: Pick<AnalysisResponse, 'circuit_data' | 'session_stats' | 'laps_data' | 'telemetry_series' | 'telemetry_summary_sent'>;
}> {
  await validateLdFileFast(file);
  await ensureWasmReady();

  const headerBytes = await readHeaderSlice(file);
  let header: ReturnType<typeof LdParser.parse_ld_header>;
  try {
    header = LdParser.parse_ld_header(headerBytes);
  } catch (e: unknown) {
    throw new Error(`Error al parsear cabecera LD: ${typeof e === 'string' ? e : String(e)}`);
  }
  const metaBytes = await readMetaSlice(file, {
    kind: 'PARSE_HEADER_OK',
    id: '',
    version: header.version,
    channelMetaOffset: header.channel_meta_offset,
    dataOffset: header.data_offset,
    session: header.session,
    venue: header.venue,
    vehicle: header.vehicle,
    driver: header.driver,
    date: header.date,
  });

  let rawChannels: ReturnType<typeof LdParser.parse_ld_channels>;
  try {
    rawChannels = LdParser.parse_ld_channels(metaBytes, header.channel_meta_offset);
  } catch (e: unknown) {
    throw new Error(`Error al parsear canales LD: ${typeof e === 'string' ? e : String(e)}`);
  }
  const channelsInfo: Array<{ name: string; shortName: string; units: string; sampleRate: number; count: number; typeId: number; dataOffset: number; dataByteLen: number; shift: number; multiplier: number; scale: number; decimalPlaces: number }> = [];
  for (let i = 0; i < rawChannels.length; i += 1) {
    const ch = rawChannels[i];
    channelsInfo.push({
      name: ch.name,
      shortName: ch.short_name,
      units: ch.units,
      sampleRate: ch.sample_rate,
      count: ch.count,
      typeId: ch.type_id,
      dataOffset: ch.data_offset,
      dataByteLen: ch.data_byte_len(),
      shift: ch.shift,
      multiplier: ch.multiplier,
      scale: ch.scale,
      decimalPlaces: ch.decimal_places,
    });
  }

  const lookup = makeLookup(channelsInfo);
  const resolved: Record<string, (typeof channelsInfo)[number] | undefined> = {};
  for (const [canonical, aliases] of Object.entries(CHANNEL_ALIASES)) {
    resolved[canonical] = aliases.map((a) => lookup.get(normalizeName(a))).find(Boolean);
  }

  const timeChannel = resolved.Session_Elapsed_Time;
  if (!timeChannel) {
    throw new Error('No se encuentra el canal de tiempo en el .ld');
  }

  const lapChannel = resolved.Lap_Number;
  if (!lapChannel) {
    throw new Error('No se encuentra el canal de vueltas en el .ld');
  }

  const previewTarget = Math.max(previewMaxSamples, analysisMaxSamples);
  const channels: Record<string, number[]> = {};
  for (const [canonical, ch] of Object.entries(resolved)) {
    if (!ch) continue;
    channels[canonical] = await readChannelSampled(file, ch, previewTarget);
  }

  const previewSampleCount = safeArray(channels, 'Session_Elapsed_Time').length;
  const alignedChannels = alignChannelsToCount(channels, previewSampleCount);
  const analysisChannels = downsampleChannels(alignedChannels, analysisMaxSamples);

  const fullTime = await readChannelSampled(file, timeChannel, timeChannel.count);
  const fullLap = await readChannelSampled(file, lapChannel, lapChannel.count);

  // Read full-resolution GPS for ms-precision lap timing via S/F line interpolation
  const gpsLatChannel = resolved.GPS_Latitude;
  const gpsLonChannel = resolved.GPS_Longitude;
  let gpsSeries: { lat: number[]; lon: number[]; sampleRate: number } | undefined;
  if (gpsLatChannel && gpsLonChannel && gpsLatChannel.sampleRate > 0) {
    const fullGpsLat = await readChannelSampled(file, gpsLatChannel, gpsLatChannel.count);
    const fullGpsLon = await readChannelSampled(file, gpsLonChannel, gpsLonChannel.count);
    if (fullGpsLat.length > 10 && fullGpsLon.length > 10) {
      gpsSeries = { lat: fullGpsLat, lon: fullGpsLon, sampleRate: gpsLatChannel.sampleRate };
    }
  }

  const preciseDurations = buildPreciseLapDurations(fullTime, fullLap, lapChannel.sampleRate, gpsSeries);

  const telemetrySeries = buildTelemetrySeries(alignedChannels);
  const lapDistances = buildLapDistances(telemetrySeries);
  const laps = filterDisplayLaps(buildLapStats(telemetrySeries, preciseDurations), lapDistances)
    .map((lap) => ({
      ...lap,
      lap_distance: lapDistances.get(lap.lap),
    }));
  const lapDurations = laps.map((l) => l.duration).filter((d) => d > 0);
  const bestLap = lapDurations.length > 0 ? Math.min(...lapDurations) : 0;
  const avgLap = lapDurations.length > 0 ? lapDurations.reduce((sum, duration) => sum + duration, 0) / lapDurations.length : 0;
  const circuitData = telemetrySeries
    .filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lon) && (Math.abs(s.lat) > 1e-6 || Math.abs(s.lon) > 1e-6))
    .map((s) => ({ lat: s.lat, lon: s.lon }));

  const derivedCircuitName = deriveCircuitNameFromFilename(file.name);

  return {
    channels: analysisChannels,
    timeCol: 'Session_Elapsed_Time',
    lapCol: 'Lap_Number',
    preview: {
      circuit_data: circuitData,
      session_stats: {
        circuit_name: header.venue || derivedCircuitName,
        total_laps: laps.length,
        best_lap_time: Number.isFinite(bestLap) ? bestLap : 0,
        avg_lap_time: Number.isFinite(avgLap) ? avgLap : 0,
        laps,
      },
      laps_data: laps,
      telemetry_series: telemetrySeries,
      telemetry_summary_sent: `Canales LD parseados en cliente: ${Object.keys(channels).length}. Sesión: ${header.session}. Circuito: ${header.venue || derivedCircuitName}.`,
    },
  };
}

function isSettingKey(key: string): boolean {
  return /^[A-Z][A-Za-z0-9]*$/.test(key);
}

function decodeSvmText(bytes: Uint8Array): string {
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) {
    return new TextDecoder('utf-16le').decode(bytes);
  }
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
    const swapped = new Uint8Array(bytes.length - 2);
    for (let i = 2; i + 1 < bytes.length; i += 2) {
      swapped[i - 2] = bytes[i + 1];
      swapped[i - 1] = bytes[i];
    }
    return new TextDecoder('utf-16le').decode(swapped);
  }
  return new TextDecoder('utf-8').decode(bytes);
}

export async function parseSvmToPreparsedSetup(file: File): Promise<{
  setup: PreparsedSetup;
  fullSetup: Record<string, SetupChange[]>;
}> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const text = decodeSvmText(bytes);
  const lines = text.split(/\r?\n/);

  const sections: Record<string, { name: string; params: Record<string, string>; read_only_params: string[] }> = {};
  let currentSection = '';

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    if (line.startsWith('[') && line.endsWith(']')) {
      currentSection = line.slice(1, -1);
      if (!sections[currentSection]) {
        sections[currentSection] = { name: currentSection, params: {}, read_only_params: [] };
      }
      continue;
    }

    if (!currentSection) continue;
    const sec = sections[currentSection];

    if (!line.startsWith('//')) {
      const idx = line.indexOf('=');
      if (idx > 0) {
        const key = line.slice(0, idx).trim();
        const value = line.slice(idx + 1).trim();
        sec.params[key] = value;
      }
      continue;
    }

    const remainder = line.slice(2);
    const idx = remainder.indexOf('=');
    if (idx > 0) {
      const key = remainder.slice(0, idx).trim();
      const value = remainder.slice(idx + 1).trim();
      if (isSettingKey(key) && !Object.prototype.hasOwnProperty.call(sec.params, key)) {
        sec.params[key] = value;
        sec.read_only_params.push(key);
      }
    }
  }

  const fullSetup: Record<string, SetupChange[]> = {};
  for (const [sectionName, sec] of Object.entries(sections)) {
    fullSetup[sectionName] = Object.entries(sec.params).map(([parameter, oldValue]) => ({
      parameter,
      old_value: oldValue,
      new_value: '',
      reason: '',
      change_pct: '',
    }));
  }

  return {
    setup: { sections },
    fullSetup,
  };
}

export async function buildPreparsedPayloadFromFiles(telemetryLdFile: File, svmFile: File): Promise<{
  payload: PreparsedAnalyzePayload;
  preview: Pick<AnalysisResponse, 'circuit_data' | 'session_stats' | 'laps_data' | 'telemetry_series' | 'telemetry_summary_sent'>;
  fullSetup: Record<string, SetupChange[]>;
}> {
  const [telemetry, setup] = await Promise.all([
    parseLdToPreparsedTelemetry(telemetryLdFile),
    parseSvmToPreparsedSetup(svmFile),
  ]);

  return {
    payload: {
      channels: telemetry.channels,
      time_col: telemetry.timeCol,
      lap_col: telemetry.lapCol,
      setup: setup.setup,
      session_stats: telemetry.preview.session_stats,
    },
    preview: telemetry.preview,
    fullSetup: setup.fullSetup,
  };
}

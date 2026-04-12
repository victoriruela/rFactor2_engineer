// Correct ADL v0 channel record reader (0x7C bytes per record)
// Maps to the Rust nom_channel_record_v0 layout:
// +0x00..+0x0F: prev/next/data_offset/count (4xu32)
// +0x10: counter u16 (ignored)
// +0x12: dtype_a u16 (ignored)
// +0x14: dtype u16 (bytes/sample: 1=i8, 2=i16, 4=i32)
// +0x16: rec_freq u16 (actual sample rate Hz)
// +0x18: legacy_shift i16 (ignored for scaling)
// +0x1A: mul i16 (actual multiplier)
// +0x1C: scale i16 (actual scale divisor)
// +0x1E: dec i16 (actual decimal places)
// +0x20: name (32 bytes)
// +0x40: short_name (8 bytes)
// +0x48: units (12 bytes)
// +0x54: marker_a i16
// +0x56: marker_b i16
// +0x58: zero_offset i16 (used as 'shift' in physical formula)
// +0x5A: marker_c i16
// +0x5C..+0x7B: padding
//
// Physical formula: (raw - zero_offset) * mul / (scale * 10^dec)

const fs = require("fs");
const buf = fs.readFileSync("data/2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld");

// Get channel_meta_offset from file header (at 0x008)
const chanMetaOff = buf.readUInt32LE(0x008);
console.log(`chan_meta_offset from header: 0x${chanMetaOff.toString(16)} = ${chanMetaOff}`);

let chanOff = chanMetaOff;
const visited = new Set();
const channels = [];

while (chanOff && !visited.has(chanOff) && chanOff + 0x7C <= buf.length) {
  visited.add(chanOff);
  const prev = buf.readUInt32LE(chanOff + 0);
  const next = buf.readUInt32LE(chanOff + 4);
  const dataOff = buf.readUInt32LE(chanOff + 8);
  const count = buf.readUInt32LE(chanOff + 0x0C);
  const counter = buf.readUInt16LE(chanOff + 0x10);
  const dtype_a = buf.readUInt16LE(chanOff + 0x12);
  const dtype = buf.readUInt16LE(chanOff + 0x14);     // bytes/sample: 1→Int8, 2→Int16, 4→Int32
  const recFreq = buf.readUInt16LE(chanOff + 0x16);   // actual sample rate Hz
  const legacyShift = buf.readInt16LE(chanOff + 0x18); // ignored for scaling
  const mul = buf.readInt16LE(chanOff + 0x1A);         // actual multiplier
  const scale = buf.readInt16LE(chanOff + 0x1C);       // actual scale divisor
  const dec = buf.readInt16LE(chanOff + 0x1E);         // decimal places
  const name = buf.slice(chanOff + 0x20, chanOff + 0x40).toString("utf8").replace(/\0/g,"").trim();
  const shortName = buf.slice(chanOff + 0x40, chanOff + 0x48).toString("utf8").replace(/\0/g,"").trim();
  const units = buf.slice(chanOff + 0x48, chanOff + 0x54).toString("utf8").replace(/\0/g,"").trim();
  const markerA = buf.readInt16LE(chanOff + 0x54);
  const markerB = buf.readInt16LE(chanOff + 0x56);
  const zeroOffset = buf.readInt16LE(chanOff + 0x58);  // the actual shift for physical formula
  const markerC = buf.readInt16LE(chanOff + 0x5A);

  // Determine typeId as WASM would
  const typeId = dtype === 1 ? 0x0008 : dtype === 2 ? 0x0001 : dtype === 4 ? 0x0004 : 0x0001;
  const sampleSize = dtype === 1 ? 1 : dtype === 4 ? 4 : 2;

  // Read first few raw samples and compute physical values
  let physSamples = [];
  let minPhys = Infinity, maxPhys = -Infinity;
  const effectiveScale = scale !== 0 ? scale : 1;
  const factor = mul / (effectiveScale * Math.pow(10, dec));

  if (dataOff > 0 && count > 0) {
    const readCount = Math.min(5, count);
    for (let i = 0; i < readCount; i++) {
      let raw;
      if (dtype === 1) raw = buf.readInt8(dataOff + i);
      else if (dtype === 4) raw = buf.readInt32LE(dataOff + i * 4);
      else raw = buf.readInt16LE(dataOff + i * 2);
      
      let phys;
      // Apply WASM-equivalent applyScaling
      if (mul === 1 && scale === 1 && dec === 0 && zeroOffset === 0) {
        phys = raw;
      } else {
        phys = (raw - zeroOffset) * mul / (effectiveScale * Math.pow(10, dec));
      }
      physSamples.push(phys.toFixed(4));
    }
    
    // Compute min/max physical for range
    for (let i = 0; i < count; i++) {
      let raw;
      if (dtype === 1) raw = buf.readInt8(dataOff + i);
      else if (dtype === 4) raw = buf.readInt32LE(dataOff + i * 4);
      else raw = buf.readInt16LE(dataOff + i * 2);
      const phys = (raw - zeroOffset) * mul / (effectiveScale * Math.pow(10, dec));
      if (phys < minPhys) minPhys = phys;
      if (phys > maxPhys) maxPhys = phys;
    }
  }

  channels.push({
    name, shortName, units, recFreq, count, dtype, typeId,
    mul, scale, dec, zeroOffset, legacyShift,
    minPhys: isFinite(minPhys) ? minPhys : null,
    maxPhys: isFinite(maxPhys) ? maxPhys : null,
    physFirst5: physSamples,
  });

  if (!next || next === chanOff) break;
  chanOff = next;
}

// Print key channels
const KEY_NAMES = /session elapsed|lap number|gear|engine rpm|ground speed|water|oil temp|fuel|throttle|brake pos/i;
console.log('\n=== KEY CHANNEL ADL V0 FIELDS ===');
for (const c of channels) {
  if (!c.name.match(KEY_NAMES)) continue;
  console.log(`\n${c.name} [${c.units}]`);
  console.log(`  dtype=${c.dtype}(sampleSize=${c.dtype===1?1:c.dtype===4?4:2}) recFreq=${c.recFreq}Hz cnt=${c.count}`);
  console.log(`  mul=${c.mul} scale=${c.scale} dec=${c.dec} zeroOffset=${c.zeroOffset} legacyShift=${c.legacyShift}`);
  console.log(`  physRange=[${c.minPhys?.toFixed(3) ?? 'null'}, ${c.maxPhys?.toFixed(3) ?? 'null'}]`);
  console.log(`  first5phys=[${c.physFirst5.join(',')}]`);
}

// Also print ALL channels compactly
console.log('\n=== ALL CHANNELS ===');
for (const c of channels) {
  console.log(`${c.name.padEnd(30)} [${c.units.padEnd(8)}] dtype=${c.dtype} rate=${c.recFreq}Hz cnt=${c.count} mul=${c.mul} scale=${c.scale} dec=${c.dec} zeroOff=${c.zeroOffset} range=[${c.minPhys?.toFixed(1) ?? '?'},${c.maxPhys?.toFixed(1) ?? '?'}]`);
}

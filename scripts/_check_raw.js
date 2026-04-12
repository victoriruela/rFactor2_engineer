// Check raw byte values at specific positions for Engine RPM and Oil Temp
// to verify what the WASM parser would actually read
const fs = require("fs");
const buf = fs.readFileSync("data/2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld");

const chanMetaOff = buf.readUInt32LE(0x008);
let chanOff = chanMetaOff;
const visited = new Set();
const chanMap = {};

while (chanOff && !visited.has(chanOff) && chanOff + 0x7C <= buf.length) {
  visited.add(chanOff);
  const next = buf.readUInt32LE(chanOff + 4);
  const dataOff = buf.readUInt32LE(chanOff + 8);
  const count = buf.readUInt32LE(chanOff + 0x0C);
  const dtype = buf.readUInt16LE(chanOff + 0x14);
  const recFreq = buf.readUInt16LE(chanOff + 0x16);
  const mul = buf.readInt16LE(chanOff + 0x1A);
  const scale = buf.readInt16LE(chanOff + 0x1C);
  const dec = buf.readInt16LE(chanOff + 0x1E);
  const name = buf.slice(chanOff + 0x20, chanOff + 0x40).toString("utf8").replace(/\0/g,"").trim();
  const zeroOffset = buf.readInt16LE(chanOff + 0x58);
  
  chanMap[name] = { chanOff, dataOff, count, dtype, recFreq, mul, scale, dec, zeroOffset };
  
  if (!next || next === chanOff) break;
  chanOff = next;
}

// For channels of interest, read actual raw bytes at specific positions
const INTERESTING = ['Engine RPM', 'Gear', 'Eng Oil Temp', 'Eng Water Temp', 'G Force Lat', 'Session Elapsed Time'];
for (const name of INTERESTING) {
  const ch = chanMap[name];
  if (!ch) { console.log(`${name}: NOT FOUND`); continue; }
  
  const sampleSize = ch.dtype === 1 ? 1 : ch.dtype === 4 ? 4 : 2;
  const effectiveScale = ch.scale !== 0 ? ch.scale : 1;
  
  console.log(`\n=== ${name} ===`);
  console.log(`  dataOff=0x${ch.dataOff.toString(16)} count=${ch.count} dtype=${ch.dtype} sampleSize=${sampleSize}Hz=${ch.recFreq}`);
  console.log(`  mul=${ch.mul} scale=${ch.scale} dec=${ch.dec} zeroOffset=${ch.zeroOffset}`);
  
  if (ch.dataOff === 0 || ch.dataOff + ch.count * sampleSize > buf.length) {
    console.log(`  ERROR: dataOff out of bounds!`);
    continue;
  }
  
  // Print first 10 raw and physical values
  console.log(`  First 10 raw/physical values:`);
  for (let i = 0; i < Math.min(10, ch.count); i++) {
    let raw;
    if (ch.dtype === 1) raw = buf.readInt8(ch.dataOff + i);
    else if (ch.dtype === 4) raw = buf.readInt32LE(ch.dataOff + i * 4);
    else raw = buf.readInt16LE(ch.dataOff + i * sampleSize);
    const rawU = ch.dtype === 2 ? buf.readUInt16LE(ch.dataOff + i * 2) : (ch.dtype === 1 ? buf.readUInt8(ch.dataOff + i) : raw);
    const phys = (raw - ch.zeroOffset) * ch.mul / (effectiveScale * Math.pow(10, ch.dec));
    const physNoOffset = raw * ch.mul / (effectiveScale * Math.pow(10, ch.dec));
    console.log(`    [${i}] raw_i16=${raw} raw_u16=${rawU}  phys(with_zeroOff)=${phys.toFixed(3)}  phys(no_zeroOff)=${physNoOffset.toFixed(3)}`);
  }
  
  // Also print values at index corresponding to MAT sample 100 (t=316s)
  // MAT sample 100 corresponds to approx 316s into the session
  // For Engine RPM at 10Hz: index ~= 316*10 = 3160
  const matIdx = Math.round(316 * ch.recFreq);
  if (matIdx < ch.count) {
    let raw;
    if (ch.dtype === 1) raw = buf.readInt8(ch.dataOff + matIdx);
    else if (ch.dtype === 4) raw = buf.readInt32LE(ch.dataOff + matIdx * 4);
    else raw = buf.readInt16LE(ch.dataOff + matIdx * sampleSize);
    const phys = (raw - ch.zeroOffset) * ch.mul / (effectiveScale * Math.pow(10, ch.dec));
    const physNoOff = raw * ch.mul / (effectiveScale * Math.pow(10, ch.dec));
    console.log(`  At t~316s (idx=${matIdx}): raw=${raw}  phys(with_zeroOff)=${phys.toFixed(3)}  phys(no_zeroOff)=${physNoOff.toFixed(3)}`);
    console.log(`  MAT reference at t=316: rpm=11419, gear=4, oil_temp=105, water_temp=92.63`);
  }
}

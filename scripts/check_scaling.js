const fs = require('fs');
const buf = fs.readFileSync('C:\\Users\\the_h\\PycharmProjects\\rFactor2_engineer\\data\\2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld');

// Traverse all channels and dump metadata for channels with scale!=0
let chanOff = 13384;
const visited = new Set();
const channels = [];

while (chanOff && !visited.has(chanOff) && chanOff < buf.length - 0x60) {
  visited.add(chanOff);
  const name = buf.slice(chanOff + 0x20, chanOff + 0x40).toString('utf8').replace(/\0/g, '').trim();
  const dataOff = buf.readUInt32LE(chanOff + 8);
  const count = buf.readUInt32LE(chanOff + 0x0C);
  const shift = buf.readInt16LE(chanOff + 0x14);
  const mult = buf.readInt16LE(chanOff + 0x16);
  const scale = buf.readInt16LE(chanOff + 0x18);
  const dec = buf.readInt16LE(chanOff + 0x1A);
  const units = buf.slice(chanOff + 0x48, chanOff + 0x54).toString('utf8').replace(/\0/g, '').trim();

  // Undocumented bytes
  const at54 = buf.readInt16LE(chanOff + 0x54);
  const at56 = buf.readInt16LE(chanOff + 0x56);
  const at58 = buf.readInt16LE(chanOff + 0x58);
  const at5A = buf.readInt16LE(chanOff + 0x5A);

  // First and last raw samples (i16)
  let firstRaw = null, lastRaw = null, minRaw = null, maxRaw = null;
  if (dataOff > 0 && count > 0 && dataOff + count * 2 <= buf.length) {
    firstRaw = buf.readInt16LE(dataOff);
    lastRaw = buf.readInt16LE(dataOff + (count - 1) * 2);
    minRaw = firstRaw;
    maxRaw = firstRaw;
    // sample min/max
    for (let i = 0; i < count; i++) {
      const v = buf.readInt16LE(dataOff + i * 2);
      if (v < minRaw) minRaw = v;
      if (v > maxRaw) maxRaw = v;
    }
  }

  channels.push({ chanOff, name, units, count, shift, mult, scale, dec, at54, at56, at58, at5A, firstRaw, lastRaw, minRaw, maxRaw });
  chanOff = buf.readUInt32LE(chanOff + 4);
}

// Print all channels with scale!=0
console.log('=== CHANNELS WITH scale!=0 ===');
for (const c of channels) {
  if (c.scale === 0) continue;
  console.log(`\n${c.name} [${c.units}] shift=${c.shift} mult=${c.mult} scale=${c.scale} dec=${c.dec}`);
  console.log(`  undoc: +0x54=${c.at54} +0x56=${c.at56} +0x58=${c.at58} +0x5A=${c.at5A}`);
  console.log(`  raw samples: first=${c.firstRaw} last=${c.lastRaw} min=${c.minRaw} max=${c.maxRaw}`);
  
  if (c.firstRaw !== null) {
    // Trial formula A: (raw - at58) * mult / (scale * 10^dec)
    const factorA = c.mult / (Math.abs(c.scale) * Math.pow(10, c.dec));
    const physA_first = (c.firstRaw - c.at58) * factorA;
    const physA_max = (c.maxRaw - c.at58) * factorA;
    console.log(`  FormulaA=(raw-at58)*mult/(scale*10^dec): first=${physA_first.toFixed(4)} max=${physA_max.toFixed(4)}`);
    
    // Trial formula B: (raw - at58) * mult / at54
    if (c.at54 !== 0) {
      const physB_first = (c.firstRaw - c.at58) * c.mult / c.at54;
      const physB_max = (c.maxRaw - c.at58) * c.mult / c.at54;
      console.log(`  FormulaB=(raw-at58)*mult/at54: first=${physB_first.toFixed(4)} max=${physB_max.toFixed(4)}`);
    }
    
    // Trial formula C: (raw - at58) / at54
    if (c.at54 !== 0) {
      const physC_first = (c.firstRaw - c.at58) / c.at54;
      const physC_max = (c.maxRaw - c.at58) / c.at54;
      console.log(`  FormulaC=(raw-at58)/at54: first=${physC_first.toFixed(4)} max=${physC_max.toFixed(4)}`);
    }
    
    // Trial formula D: (raw - at58) / scale  (ignore mult and dec)
    const physD_first = (c.firstRaw - c.at58) / c.scale;
    const physD_max = (c.maxRaw - c.at58) / c.scale;
    console.log(`  FormulaD=(raw-at58)/scale: first=${physD_first.toFixed(4)} max=${physD_max.toFixed(4)}`);
    
    // For GS specifically: expected max = 324 km/h, first = 0
    if (c.name.includes('Ground Speed')) {
      const empirical = 0.019744;
      const physE_first = (c.firstRaw - c.at58) * empirical;
      const physE_max = (c.maxRaw - c.at58) * empirical;
      console.log(`  Empirical*0.019744: first=${physE_first.toFixed(4)} max=${physE_max.toFixed(4)}`);
    }
  }
}

// Now print SE channel physical calcs
console.log('\n=== SPECIAL: Session Elapsed Time ===');
const se = channels.find(c => c.name.includes('Session Elapsed'));
if (se) {
  const dataOff = buf.readUInt32LE(13384 + 4); // find SE data offset
  console.log(`SE at58=${se.at58} scale=${se.scale}`);
  console.log(`SE[0] raw=${se.firstRaw} + at58=${se.at58}: ${se.firstRaw-se.at58}`);
  console.log(`SE[0] raw=${se.firstRaw} + scale=${se.scale}: ${se.firstRaw+se.scale}`);
  console.log(`SE max_raw=${se.maxRaw}: phys_via_at58=${se.maxRaw-se.at58} phys_via_scale=${se.maxRaw+se.scale}`);
}

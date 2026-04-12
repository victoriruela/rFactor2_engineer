const fs = require("fs");
const buf = fs.readFileSync("data/2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld");
let chanOff = 13384;
const visited = new Set();
while (chanOff && !visited.has(chanOff) && chanOff < buf.length - 0x1A8) {
  visited.add(chanOff);
  const typeId = buf.readUInt16LE(chanOff + 0x10);
  const sampleRate = buf.readUInt16LE(chanOff + 0x12);
  const count = buf.readUInt32LE(chanOff + 0x0C);
  const shift = buf.readInt16LE(chanOff + 0x14);
  const mult = buf.readInt16LE(chanOff + 0x16);
  const scale = buf.readInt16LE(chanOff + 0x18);
  const dec = buf.readInt16LE(chanOff + 0x1A);
  const name = buf.slice(chanOff + 0x20, chanOff + 0x40).toString("utf8").replace(/\0/g,"").trim();
  const units = buf.slice(chanOff + 0x44, chanOff + 0x50).toString("utf8").replace(/\0/g,"").trim();
  const dataOff = buf.readUInt32LE(chanOff + 8);

  // Only check interesting channels
  if (!name.match(/Session Elapsed|Lap Number|Engine RPM|Gear|Oil Temp|Water Temp|Ground Speed/i)) {
    chanOff = buf.readUInt32LE(chanOff + 4);
    continue;
  }

  // Read first 5 samples based on typeId
  let rawSamples = [];
  let physSamples = [];
  const sampleSize = typeId === 0 ? 4 : (typeId === 7 ? 8 : 2);

  for (let i = 0; i < Math.min(5, count); i++) {
    let raw, phys;
    switch (typeId) {
      case 0: // f32
        raw = buf.readFloatLE(dataOff + i * 4);
        phys = raw; // already physical
        break;
      case 1: // i16
        raw = buf.readInt16LE(dataOff + i * 2);
        phys = scale !== 0 ? (raw - shift) * mult / (scale * Math.pow(10, dec)) : raw;
        break;
      case 2: // u16
        raw = buf.readUInt16LE(dataOff + i * 2);
        phys = scale !== 0 ? (raw - shift) * mult / (scale * Math.pow(10, dec)) : raw;
        break;
      default:
        raw = phys = 0;
    }
    rawSamples.push(raw.toFixed(4));
    physSamples.push(phys.toFixed(4));
  }

  // Also compute min/max physical for range check
  let minPhys = Infinity, maxPhys = -Infinity;
  for (let i = 0; i < count; i++) {
    let phys;
    switch (typeId) {
      case 0: phys = buf.readFloatLE(dataOff + i * 4); break;
      case 1: { const r = buf.readInt16LE(dataOff + i * 2); phys = scale !== 0 ? (r - shift) * mult / (scale * Math.pow(10, dec)) : r; break; }
      case 2: { const r = buf.readUInt16LE(dataOff + i * 2); phys = scale !== 0 ? (r - shift) * mult / (scale * Math.pow(10, dec)) : r; break; }
      default: phys = 0;
    }
    if (phys < minPhys) minPhys = phys;
    if (phys > maxPhys) maxPhys = phys;
  }

  console.log(`${name.padEnd(30)} [${units.padEnd(5)}] typeId=0x${typeId.toString(16).padStart(4,"0")} rate=${sampleRate}Hz cnt=${count} shift=${shift} mult=${mult} scale=${scale} dec=${dec}`);
  console.log(`  physRange=[${minPhys.toFixed(3)}, ${maxPhys.toFixed(3)}]  first5phys=[${physSamples.join(",")}]`);

  chanOff = buf.readUInt32LE(chanOff + 4);
}

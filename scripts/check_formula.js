const fs = require('fs');
const buf = fs.readFileSync('C:\\Users\\the_h\\PycharmProjects\\rFactor2_engineer\\data\\2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld');

// Traverse all channels 
let chanOff = 13384;
const visited = new Set();
while (chanOff && !visited.has(chanOff) && chanOff < buf.length - 0x60) {
  visited.add(chanOff);
  const name = buf.slice(chanOff+0x20, chanOff+0x40).toString('utf8').replace(/\0/g,'').trim();
  const dataOff = buf.readUInt32LE(chanOff+8);
  const count = buf.readUInt32LE(chanOff+0x0C);
  const shift = buf.readInt16LE(chanOff+0x14);
  const mult = buf.readInt16LE(chanOff+0x16);
  const scale = buf.readInt16LE(chanOff+0x18);
  const dec = buf.readInt16LE(chanOff+0x1A);
  const units = buf.slice(chanOff+0x48, chanOff+0x54).toString('utf8').replace(/\0/g,'').trim();
  const at54 = buf.readInt16LE(chanOff+0x54);
  const at58 = buf.readInt16LE(chanOff+0x58);

  if (scale !== 0 && count > 0) {
    let minRaw = buf.readInt16LE(dataOff);
    let maxRaw = minRaw;
    for (let i = 0; i < count; i++) {
      const v = buf.readInt16LE(dataOff + i * 2);
      if (v < minRaw) minRaw = v;
      if (v > maxRaw) maxRaw = v;
    }
    // FormulaA: (raw-at58)*mult/(scale*10^dec) 
    const factorA = mult / (Math.abs(scale) * Math.pow(10, dec));
    const physA = (maxRaw - at58) * factorA;
    // FormulaE: at54_phys = at54 / (mult*dec-1) [the 6147/19=323.5 km/h hypothesis]
    const physE = at54 / (mult * dec - 1);
    // FormulaF: at54 directly as physical max
    const physF = at54;
    // the range between at58 and maxRaw:
    const rawRange = maxRaw - at58;
    const line = name.padEnd(25) + ' [' + units.padEnd(5) + ']'
      + ' mult=' + String(mult).padStart(3)
      + ' scale=' + String(scale).padStart(6) 
      + ' dec=' + dec
      + '  at54=' + String(at54).padStart(7)
      + '  physA=' + physA.toFixed(2).padStart(8)
      + '  at54/(m*d-1)=' + physE.toFixed(2).padStart(8)
      + '  at54_direct=' + physF;
    console.log(line);
  }
  chanOff = buf.readUInt32LE(chanOff+4);
}

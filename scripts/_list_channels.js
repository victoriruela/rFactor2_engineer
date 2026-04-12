const fs = require("fs");
const buf = fs.readFileSync("data/2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld");
let chanOff = 13384;
const visited = new Set();
const results = [];
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
  const shortName = buf.slice(chanOff + 0x3C, chanOff + 0x44).toString("utf8").replace(/\0/g,"").trim();
  const units = buf.slice(chanOff + 0x44, chanOff + 0x50).toString("utf8").replace(/\0/g,"").trim();
  const dataOff = buf.readUInt32LE(chanOff + 8);
  
  // Read first physical sample
  let phys0 = null;
  if (dataOff > 0 && count > 0) {
    if (typeId === 0 && dataOff + 4 <= buf.length) {
      phys0 = buf.readFloatLE(dataOff).toFixed(4);
    } else if (typeId === 1 && dataOff + 2 <= buf.length) {
      const raw = buf.readInt16LE(dataOff);
      phys0 = (scale !== 0 ? (raw - shift) * mult / (scale * Math.pow(10, dec)) : raw).toFixed(4);
    } else if (typeId === 2 && dataOff + 2 <= buf.length) {
      const raw = buf.readUInt16LE(dataOff);
      phys0 = (scale !== 0 ? (raw - shift) * mult / (scale * Math.pow(10, dec)) : raw).toFixed(4);
    }
  }
  
  results.push(`${name.padEnd(35)} short="${shortName.padEnd(8)}" units=[${units.padEnd(8)}] tid=0x${typeId.toString(16)} rate=${sampleRate}Hz cnt=${count} shift=${shift} mult=${mult} scale=${scale} dec=${dec} phys0=${phys0}`);
  chanOff = buf.readUInt32LE(chanOff + 4);
}
fs.writeFileSync("scripts/_channels_list.txt", results.join("\n") + "\n");
console.log("Written", results.length, "channels to scripts/_channels_list.txt");

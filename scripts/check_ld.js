const fs = require('fs');
const buf = fs.readFileSync('data/2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld');

// Read MAT json reference values
const matJson = JSON.parse(fs.readFileSync('data/con mat.json', 'utf8'));
if (matJson.telemetry_series && matJson.telemetry_series.length > 0) {
  console.log('MAT telemetry_series[0]:', JSON.stringify(matJson.telemetry_series[0]));
  console.log('MAT telemetry_series[1]:', JSON.stringify(matJson.telemetry_series[1]));
}

// Session stats from MAT (reference)
if (matJson.session_stats) {
  console.log('MAT session_stats:', JSON.stringify(matJson.session_stats[0]));
}

// Now find LD channels
const FIRST_CHAN = 0x3448;
let chanOff = FIRST_CHAN;
const visited = new Set();
const chanMap = {};
while (chanOff && !visited.has(chanOff) && chanOff < buf.length - 0x60) {
  visited.add(chanOff);
  const dataOff = buf.readUInt32LE(chanOff + 8);
  const count = buf.readUInt32LE(chanOff + 0xC);
  const shift = buf.readInt16LE(chanOff + 0x14);
  const mult = buf.readInt16LE(chanOff + 0x16);
  const scale = buf.readInt16LE(chanOff + 0x18);
  const dec = buf.readInt16LE(chanOff + 0x1A);
  const name = buf.slice(chanOff + 0x20, chanOff + 0x40).toString('utf8').replace(/\0/g, '').trim();
  const units = buf.slice(chanOff + 0x48, chanOff + 0x54).toString('utf8').replace(/\0/g, '').trim();
  chanMap[name] = { dataOff, count, shift, mult, scale, dec, units, chanOff };
  chanOff = buf.readUInt32LE(chanOff + 4);
}

console.log('\nChannel list:');
for (const [name, c] of Object.entries(chanMap)) {
  const r0 = buf.readInt16LE(c.dataOff);
  const u0 = buf.readUInt16LE(c.dataOff);
  console.log(`  ${name.padEnd(30)} cnt=${c.count} shift=${c.shift} mult=${c.mult} scale=${c.scale} dec=${c.dec} [${c.units}] raw0_i16=${r0} raw0_u16=${u0}`);
}

// Find LapNumber and Ground Speed channels by traversing the list
// Dump header bytes to find first channel pointer
console.log('Header bytes at various offsets:');
for (let o = 0x3a0; o < 0x3c0; o += 4) {
  const v = buf.readUInt32LE(o);
  if (v > 0x1000 && v < buf.length) console.log('  0x'+o.toString(16)+': 0x'+v.toString(16)+' ('+v+')');
}

// Known first channel is at 0x3448 from previous investigation
const FIRST_CHAN = 0x3448;

// Traverse all channels starting from known first channel
let chanOff = FIRST_CHAN;
let lapChanInfo = null, gsChanInfo = null, seChanInfo = null;
let visited = new Set();
while (chanOff !== 0 && !visited.has(chanOff) && chanOff < buf.length - 0x60) {
  visited.add(chanOff);
  const prev = buf.readUInt32LE(chanOff + 0);
  const next = buf.readUInt32LE(chanOff + 4);
  const dataOff = buf.readUInt32LE(chanOff + 8);
  const count = buf.readUInt32LE(chanOff + 0xC);
  const typeId = buf.readUInt16LE(chanOff + 0x10);
  const shift = buf.readInt16LE(chanOff + 0x14);
  const mult = buf.readInt16LE(chanOff + 0x16);
  const scale = buf.readInt16LE(chanOff + 0x18);
  const dec = buf.readInt16LE(chanOff + 0x1A);
  const name = buf.slice(chanOff + 0x20, chanOff + 0x40).toString('utf8').replace(/\0/g,'').trim();
  const units = buf.slice(chanOff + 0x48, chanOff + 0x54).toString('utf8').replace(/\0/g,'').trim();
  //console.log('Chan 0x'+chanOff.toString(16)+': '+name+' ['+units+'] dataOff=0x'+dataOff.toString(16)+' cnt='+count+' shift='+shift+' mult='+mult+' scale='+scale+' dec='+dec);
  if (name === 'Lap Number') lapChanInfo = {chanOff, dataOff, count, shift, mult, scale, dec, units};
  if (name === 'Ground Speed') gsChanInfo = {chanOff, dataOff, count, shift, mult, scale, dec, units};
  if (name === 'Session Elapsed Time') seChanInfo = {chanOff, dataOff, count, shift, mult, scale, dec, units};
  chanOff = next;
}

console.log('LapNumber:', JSON.stringify(lapChanInfo));
console.log('GroundSpeed:', JSON.stringify(gsChanInfo));
console.log('SessionElapsedTime:', JSON.stringify(seChanInfo));

if (!lapChanInfo || !gsChanInfo || !seChanInfo) { console.log('MISSING CHANNELS'); process.exit(1); }

const lapOff = lapChanInfo.dataOff;
const lapCount = lapChanInfo.count;
const lapShift = lapChanInfo.shift, lapMult = lapChanInfo.mult, lapScale = lapChanInfo.scale, lapDec = lapChanInfo.dec;

const seOff = seChanInfo.dataOff;
const seScale = seChanInfo.scale, seMult = seChanInfo.mult, seDec = seChanInfo.dec, seShift = seChanInfo.shift;
const gsOff = gsChanInfo.dataOff;
const gsScale = gsChanInfo.scale, gsMult = gsChanInfo.mult, gsDec = gsChanInfo.dec, gsShift = gsChanInfo.shift;

// Rate: GS is 10Hz (37014/3700s), SE/Lap is 50Hz
const gsRate = 10, lapRate = 50;

// Debug: print first few lap values
console.log('\nFirst 5 lap values:');
for (let i = 0; i < 5; i++) {
  const rawLap = buf.readInt16LE(lapOff + i * 2);
  const physLap = (rawLap + lapShift) * lapMult / (lapScale * Math.pow(10, lapDec));
  console.log('  sample '+i+': raw_i16='+rawLap+' raw_u16='+buf.readUInt16LE(lapOff+i*2)+' lap='+physLap.toFixed(4));
}
console.log('\nFirst few SE values:');
for (let i = 0; i < 5; i++) {
  const rawSE = buf.readInt16LE(seOff + i * 2);
  const physSE = (rawSE + seShift) * seMult / (seScale * Math.pow(10, seDec));
  console.log('  sample '+i+': raw_i16='+rawSE+' se='+physSE.toFixed(4)+'s');
}

// Scan lap channel at 50Hz, look for lap transitions (start: -5, race: 1..40)
let lastLap = -999;
for (let i = 0; i < lapCount; i += 50) {
  const rawLap = buf.readInt16LE(lapOff + i * 2);
  const phys = (rawLap + lapShift) * lapMult / (lapScale * Math.pow(10, lapDec));
  const lapRound = Math.round(phys);
  if (lapRound !== lastLap && lapRound >= -6 && lapRound <= 60) {
    const tRaw = buf.readInt16LE(seOff + i * 2);
    const t = (tRaw + seShift) * seMult / (seScale * Math.pow(10, seDec));
    const gsIdx = Math.floor(i * 10 / 50);
    const gsRaw = buf.readInt16LE(gsOff + gsIdx * 2);
    const gsPhys = (gsRaw + gsShift) * gsMult / (gsScale * Math.pow(10, gsDec));
    console.log('Lap='+phys.toFixed(3)+' round='+lapRound+' sample='+i+' t='+t.toFixed(2)+'s speed='+gsPhys.toFixed(1)+' km/h raw_gs='+buf.readUInt16LE(gsOff + gsIdx * 2));
    lastLap = lapRound;
  }
}

// Scan for max ground speed anywhere in the file
console.log('\n--- Ground speed stats across all 37014 samples ---');
let maxGs = -999, maxIdx = -1;
for (let i = 0; i < gsChanInfo.count; i++) {
  const gsRaw = buf.readInt16LE(gsOff + i * 2);
  const gs = (gsRaw + gsShift) * gsMult / (gsScale * Math.pow(10, gsDec));
  if (gs > maxGs) { maxGs = gs; maxIdx = i; }
}
console.log('Max speed anywhere: '+maxGs.toFixed(1)+' km/h at sample '+maxIdx);
// Also show a few samples around the max
const startI = Math.max(0, maxIdx - 2);
const endI = Math.min(gsChanInfo.count - 1, maxIdx + 2);
for (let i = startI; i <= endI; i++) {
  const gsRaw = buf.readInt16LE(gsOff + i * 2);
  const gs = (gsRaw + gsShift) * gsMult / (gsScale * Math.pow(10, gsDec));
  console.log('  gs['+i+'] raw_i16='+gsRaw+' raw_u16='+buf.readUInt16LE(gsOff+i*2)+' => '+gs.toFixed(2)+' km/h');
}

// Also print raw_u16 of GS at sample 3000 (should be ~3000/10=300s into session → during first racing lap)
console.log('\nGS at sample 3000 (300s mark):');
const gsSample3000 = buf.readInt16LE(gsOff + 3000 * 2);
console.log('raw_i16='+gsSample3000+' raw_u16='+buf.readUInt16LE(gsOff+3000*2)+' => '+((gsSample3000+gsShift)*gsMult/(gsScale*Math.pow(10,gsDec))).toFixed(2)+' km/h');

const fs = require('fs');
const buf = Buffer.from(fs.readFileSync('data/2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld'));

const channels = [];
let off = 0x3448;
for (let i = 0; i < 100; i++) {
  const name = buf.slice(off+32, off+64).toString('ascii').replace(/\0/g,'').trim();
  channels.push({off, name});
  const next = buf.readUInt32LE(off+4);
  if (!next) break;
  off = next;
}

const gsOff = channels.find(c=>c.name==='Ground Speed')?.off;
const thrOff = channels.find(c=>c.name==='Throttle Pos')?.off;
const btOff = channels.find(c=>c.name==='Brake Temp FL')?.off;
const tpOff = channels.find(c=>c.name==='Tyre Pressure FL')?.off;

const fields = [
  {off:0x00, size:4, name:'prev_offset'},
  {off:0x04, size:4, name:'next_offset'},
  {off:0x08, size:4, name:'data_offset'},
  {off:0x0C, size:4, name:'count'},
  {off:0x10, size:2, name:'type_id(u16)'},
  {off:0x12, size:2, name:'freq(u16)'},
  {off:0x14, size:2, name:'field_A(i16)'},
  {off:0x16, size:2, name:'field_B(i16)'},
  {off:0x18, size:2, name:'field_C(i16)'},
  {off:0x1A, size:2, name:'field_D(i16)'},
  {off:0x1C, size:2, name:'extra1(u16)'},
  {off:0x1E, size:2, name:'extra2(u16)'},
  {off:0x20, size:32, name:'name'},
  {off:0x40, size:8, name:'short_name'},
  {off:0x48, size:12, name:'units'},
  {off:0x54, size:2, name:'at54(i16)'},
  {off:0x56, size:2, name:'at56(i16)'},
  {off:0x58, size:2, name:'at58(i16)'},
  {off:0x5A, size:2, name:'at5A(i16)'},
];

function hexDump(start, label) {
  console.log('\n--- ' + label + ' @ 0x' + start.toString(16) + ' ---');
  for (const f of fields) {
    const bytes = buf.slice(start+f.off, start+f.off+Math.min(f.size,12));
    const hex = Array.from(bytes).map(b=>b.toString(16).padStart(2,'0')).join(' ');
    let val = '';
    if (f.name.includes('i16')) {
      val = ' = ' + buf.readInt16LE(start+f.off);
    } else if (f.name.includes('u16')) {
      val = ' = ' + buf.readUInt16LE(start+f.off);
    } else if (f.size===4) {
      val = ' = 0x' + buf.readUInt32LE(start+f.off).toString(16) + ' (' + buf.readUInt32LE(start+f.off) + ')';
    } else if (f.name.includes('name') || f.name.includes('units')) {
      val = ' = "' + bytes.toString('ascii').replace(/\0/g,'') + '"';
    }
    console.log('  +0x'+f.off.toString(16).padStart(2,'0')+' ['+f.name.padEnd(14)+'] ' + hex.padEnd(35) + val);
  }
}

hexDump(thrOff, 'Throttle Pos');
hexDump(gsOff, 'Ground Speed');
hexDump(btOff, 'Brake Temp FL');
hexDump(tpOff, 'Tyre Pressure FL');

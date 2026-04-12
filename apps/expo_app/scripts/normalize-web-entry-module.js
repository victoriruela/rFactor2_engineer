const fs = require('fs');
const path = require('path');

const distIndex = path.resolve(__dirname, '..', 'dist', 'index.html');

if (!fs.existsSync(distIndex)) {
  console.error(`No se encontro ${distIndex}`);
  process.exit(1);
}

const html = fs.readFileSync(distIndex, 'utf8');
const normalized = html.replace(
  /<script\s+src="\/_expo\/static\/js\/web\/entry-[a-f0-9]+\.js"\s+defer><\/script>/i,
  (match) => (match.includes('type="module"') ? match : match.replace('<script ', '<script type="module" ')),
);

if (normalized !== html) {
  fs.writeFileSync(distIndex, normalized, 'utf8');
  console.log('index.html normalizado a script type=module');
} else if (/type="module"/.test(html)) {
  console.log('index.html ya estaba en type=module');
} else {
  console.error('No se pudo normalizar index.html: no se encontro el script entry esperado');
  process.exit(1);
}

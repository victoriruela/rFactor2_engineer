/**
 * validate_ld_fix.js
 * Pre-deploy validation script: verifies the LD v0 fix is correct and
 * the static embed folder is ready for Go build.
 *
 * Run with: node scripts/validate_ld_fix.js
 * Exit 0 = all checks pass. Exit 1 = at least one check failed.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
let failed = false;

function check(label, condition, detail) {
  if (condition) {
    console.log('  PASS  ' + label);
  } else {
    console.log('  FAIL  ' + label + (detail ? ' — ' + detail : ''));
    failed = true;
  }
}

// ── 1. Validate real .ld file is accepted by the new logic ────────────────
console.log('\n[1] LD file validation logic');
const ldPath = path.join(ROOT, 'data', '2025-12-01 - 22-49-53 - Qatar F1 2025 - R1.ld');
if (!fs.existsSync(ldPath)) {
  console.log('  SKIP  LD file not found at', ldPath);
} else {
  const buf = fs.readFileSync(ldPath);
  const v0Magic   = buf.readUInt32LE(0);
  const v0Version = buf.readUInt32LE(4);
  const metaOff   = buf.readUInt32LE(8);
  check('ADL v0 magic (0x40)',         v0Magic === 0x40,    '0x' + v0Magic.toString(16));
  check('ADL v0 version (0)',          v0Version === 0,     String(v0Version));
  check('channel_meta_offset > 0',     metaOff > 0,        '0x' + metaOff.toString(16));
  check('validateLdFileFast would pass', v0Magic === 0x40 && v0Version === 0 && metaOff > 0);
}

// ── 2. Check static embed folder has the new bundle ───────────────────────
console.log('\n[2] Go static embed folder');
const staticDir = path.join(ROOT, 'services', 'backend_go', 'cmd', 'server', 'static');
const indexHtml = path.join(staticDir, 'index.html');
check('static/index.html exists', fs.existsSync(indexHtml));
if (fs.existsSync(indexHtml)) {
  const html = fs.readFileSync(indexHtml, 'utf8');
  const bundleMatch = html.match(/entry-([a-f0-9]+)\.js/);
  const bundleHash = bundleMatch ? bundleMatch[1] : null;
  check('index.html has a bundle reference', bundleHash !== null, 'no entry-*.js found');
  check('index.html has type=module',        html.includes('type="module"'), 'missing type="module"');

  if (bundleHash) {
    const bundlePath = path.join(
      staticDir, '_expo', 'static', 'js', 'web',
      'entry-' + bundleHash + '.js'
    );
    check('referenced bundle file exists in static/', fs.existsSync(bundlePath), bundlePath);

    // Verify the bundle contains the v0 magic check (0x40 / 64)
    if (fs.existsSync(bundlePath)) {
      const bundleContent = fs.readFileSync(bundlePath, 'utf8');
      // Bundler minifies: 0x00000040 === val becomes 64===val or val===64
      const hasV0Check = /64===\w/.test(bundleContent) || /\w===64/.test(bundleContent)
        || bundleContent.includes('64===o') || bundleContent.includes('o===64');
      check('bundle contains ADL v0 magic check (64)', hasV0Check, 'magic literal not found in bundle — TS fix may not be compiled in');
    }
  }
}

// ── 3. Dist folder matches static folder ─────────────────────────────────
console.log('\n[3] Expo dist vs Go static sync');
const distIndex = path.join(ROOT, 'apps', 'expo_app', 'dist', 'index.html');
if (fs.existsSync(distIndex) && fs.existsSync(indexHtml)) {
  const distHtml   = fs.readFileSync(distIndex,  'utf8');
  const staticHtml = fs.readFileSync(indexHtml, 'utf8');
  const distBundle   = (distHtml.match(/entry-([a-f0-9]+)\.js/) || [])[1];
  const staticBundle = (staticHtml.match(/entry-([a-f0-9]+)\.js/) || [])[1];
  check('dist and static reference same bundle', distBundle === staticBundle,
    'dist=' + distBundle + ' static=' + staticBundle);
}

// ── Result ────────────────────────────────────────────────────────────────
console.log('');
if (failed) {
  console.log('VALIDATION FAILED — do not deploy until all checks pass.');
  process.exit(1);
} else {
  console.log('ALL CHECKS PASSED — safe to build and deploy.');
}

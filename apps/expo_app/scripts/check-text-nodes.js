/**
 * check-text-nodes.js
 * Static analysis: finds potential "Unexpected text node in View" patterns in TSX files.
 * Run: node scripts/check-text-nodes.js
 */
const fs = require('fs');
const path = require('path');

// --- Config ---
const ROOT = path.resolve(__dirname, '..');
const EXTENSIONS = ['.tsx', '.ts'];

// View-like components whose children must NOT be raw text
const VIEW_LIKE = new Set([
  'View', 'ScrollView', 'FlatList', 'Pressable', 'TouchableOpacity',
  'TouchableHighlight', 'SafeAreaView', 'KeyboardAvoidingView',
  'SectionList', 'VirtualizedList', 'ImageBackground',
]);

// Text-safe components (their children can be strings)
const TEXT_LIKE = new Set(['Text', 'SvgText', 'TextInput', 'Button']);

function collectTsxFiles(dir) {
  const results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isDirectory() && entry.name !== 'node_modules' && entry.name !== '.expo' && entry.name !== 'dist') {
      results.push(...collectTsxFiles(path.join(dir, entry.name)));
    } else if (entry.isFile() && EXTENSIONS.includes(path.extname(entry.name))) {
      results.push(path.join(dir, entry.name));
    }
  }
  return results;
}

function analyzeFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const issues = [];

  // Track the component tag stack (simplified)
  // This is heuristic-based, not a full AST parser
  const tagStack = [];
  let inTextContext = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;
    const trimmed = line.trim();

    // Detect opening tags
    const openTagMatch = trimmed.match(/^<([A-Z][A-Za-z]*)/);
    if (openTagMatch) {
      const tag = openTagMatch[1];
      const isSelfClosing = trimmed.endsWith('/>') || trimmed.endsWith('/ >');
      if (!isSelfClosing) {
        tagStack.push(tag);
        inTextContext = TEXT_LIKE.has(tag);
      }
    }

    // Detect closing tags
    const closeTagMatch = trimmed.match(/^<\/([A-Z][A-Za-z]*)\s*>/);
    if (closeTagMatch) {
      const tag = closeTagMatch[1];
      if (tagStack.length > 0 && tagStack[tagStack.length - 1] === tag) {
        tagStack.pop();
        const parent = tagStack.length > 0 ? tagStack[tagStack.length - 1] : null;
        inTextContext = parent ? TEXT_LIKE.has(parent) : false;
      }
    }

    // Now check for problematic patterns
    const currentTag = tagStack.length > 0 ? tagStack[tagStack.length - 1] : null;
    const inViewContext = currentTag && VIEW_LIKE.has(currentTag) && !inTextContext;

    if (inViewContext) {
      // Pattern 1: {' '} or {" "} or {'\n'} etc directly in View
      if (/{['"]\s*['"]}/g.test(trimmed) || /\{["'`][^"'`]*["'`]\}/g.test(trimmed)) {
        // Check it's not inside a component prop (=)
        if (!trimmed.match(/\w+={/) && !trimmed.match(/style=/)  && !trimmed.match(/title=/) && !trimmed.match(/label=/)) {
          issues.push({ file: filePath, line: lineNum, type: 'string-expr-in-view', text: trimmed });
        }
      }
    }

    // Pattern 2: {' '} anywhere in TSX (flag for review)
    if (/\{['"][^'"]+['"]\}/.test(trimmed) && !trimmed.includes('<Text') && !trimmed.includes('style=')) {
      // Only care if it's in a JSX context (has < or > nearby)
      const surroundingContent = lines.slice(Math.max(0, i-2), Math.min(lines.length, i+3)).join('\n');
      if (surroundingContent.includes('<View') || surroundingContent.includes('<ScrollView') || 
          surroundingContent.includes('<Pressable')) {
        // Check if we are NOT inside a Text component
        const viewMatch = surroundingContent.match(/<(View|ScrollView|Pressable)[^>]*>/);
        const textMatch = surroundingContent.match(/<Text[^>]*>/);
        if (viewMatch && !textMatch) {
          issues.push({ file: filePath, line: lineNum, type: 'string-expr-near-view', text: trimmed });
        }
      }
    }

    // Pattern 3: JSX string literals directly in View (text not in {}) 
    // e.g.: <View>Some text here</View>
    // Look for lines that have text but are not JSX attributes or comments
    if (currentTag && VIEW_LIKE.has(currentTag) && !inTextContext) {
      // A line that's just plain text (no JSX tags, not a comment, not an attribute)
      if (!trimmed.startsWith('<') && !trimmed.startsWith('{') && !trimmed.startsWith('//') && 
          !trimmed.startsWith('*') && trimmed.length > 0 && !trimmed.startsWith(')') &&
          !trimmed.startsWith(']') && !trimmed.startsWith('return') && !trimmed.startsWith('const') &&
          !trimmed.startsWith('let') && !trimmed.startsWith('if') && !trimmed.startsWith('default') &&
          !trimmed.startsWith('.') && !trimmed.includes('=>') && !trimmed.includes('style') &&
          !trimmed.startsWith('...') && !trimmed.includes(':') && /[a-zA-Z]/.test(trimmed)) {
        issues.push({ file: filePath, line: lineNum, type: 'raw-text-in-view', text: trimmed });
      }
    }
  }

  return issues;
}

// --- Main ---
const files = collectTsxFiles(ROOT);
let totalIssues = 0;

console.log(`Scanning ${files.length} TypeScript/TSX files...\n`);

for (const file of files) {
  const issues = analyzeFile(file);
  if (issues.length > 0) {
    const relPath = path.relative(ROOT, file);
    console.log(`\nFILE: ${relPath}`);
    for (const issue of issues) {
      console.log(`  Line ${issue.line} [${issue.type}]: ${issue.text.substring(0, 120)}`);
      totalIssues++;
    }
  }
}

console.log(`\n--- Total potential issues: ${totalIssues} ---`);
if (totalIssues === 0) {
  console.log('No obvious text-node-in-View patterns found by heuristic analysis.');
  console.log('The issue may be more subtle - try writing Jest tests with jest-expo/web preset.');
}

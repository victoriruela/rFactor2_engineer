// metro.config.js
// Extends default Metro config to:
//  1. Treat .wasm files as binary assets (Metro copies them to the output
//     directory and gives us a URL string back from require()).
//  2. Keep all existing Expo defaults intact.

const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// Register .wasm as a binary asset extension so Metro copies it to dist/
// and resolves require('*.wasm') to its served URL path.
config.resolver.assetExts.push('wasm');

module.exports = config;

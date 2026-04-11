// Ambient declaration so TypeScript accepts bare WASM asset imports.
// Metro resolves these to a URL string (via the assetExts config in metro.config.js).
declare module '*.wasm' {
  const url: string;
  export default url;
}

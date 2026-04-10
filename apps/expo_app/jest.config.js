// jest.config.js
// Use jest-expo/web preset so tests run with react-native-web, which throws
// "Unexpected text node" errors — the same as the browser does.
module.exports = {
  preset: 'jest-expo/web',
  setupFiles: ['<rootDir>/__mocks__/setup.js'],
  moduleNameMapper: {
    // Expo router mocks
    '^expo-router$': '<rootDir>/__mocks__/expo-router.js',
    '^expo-router/(.*)$': '<rootDir>/__mocks__/expo-router.js',
    // SVG mock (react-native-svg not available in jsdom)
    '^react-native-svg$': '<rootDir>/__mocks__/react-native-svg.js',
    // Static assets
    '\\.(png|jpg|jpeg|gif|webp|svg)$': '<rootDir>/__mocks__/fileMock.js',
  },
};

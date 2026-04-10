// Mock for expo-router
const React = require('react');

const useRouter = () => ({
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  navigate: jest.fn(),
});

const useLocalSearchParams = () => ({});
const usePathname = () => '/';
const useSegments = () => [];
const useFocusEffect = jest.fn();
const useNavigation = () => ({});

const Link = ({ children }) => React.createElement('span', null, children);
const Redirect = () => null;
const Slot = ({ children }) => React.createElement('div', null, children);
const Stack = { Screen: () => null };
const Tabs = ({ children, screenOptions }) => React.createElement('div', null, children);
Tabs.Screen = ({ name, options }) => null;

const router = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
};

module.exports = {
  useRouter,
  useLocalSearchParams,
  usePathname,
  useSegments,
  useFocusEffect,
  useNavigation,
  Link,
  Redirect,
  Slot,
  Stack,
  Tabs,
  router,
};

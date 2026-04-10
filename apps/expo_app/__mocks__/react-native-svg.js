// Mock for react-native-svg
const React = require('react');

const createSvgElement = (displayName) => {
  const Component = ({ children, ...props }) => React.createElement('svg', null, children);
  Component.displayName = displayName;
  return Component;
};

const Svg = createSvgElement('Svg');
const Line = createSvgElement('Line');
const Polyline = createSvgElement('Polyline');
const Rect = createSvgElement('Rect');
const Circle = createSvgElement('Circle');
const Text = createSvgElement('SvgText');
const Path = createSvgElement('Path');
const G = createSvgElement('G');
const Defs = createSvgElement('Defs');
const ClipPath = createSvgElement('ClipPath');
const LinearGradient = createSvgElement('LinearGradient');
const Stop = createSvgElement('Stop');

module.exports = {
  default: Svg,
  Svg,
  Line,
  Polyline,
  Rect,
  Circle,
  Text,
  Path,
  G,
  Defs,
  ClipPath,
  LinearGradient,
  Stop,
};

/**
 * MarkdownText — lightweight renderer supporting **bold** and \n line breaks.
 * Designed for React Native Web (no external dependencies).
 */
import React from 'react';
import { Text, StyleSheet, View } from 'react-native';

interface Props {
  text: string;
  style?: object;
}

interface Segment {
  text: string;
  bold: boolean;
}

function parseSegments(raw: string): Segment[] {
  const segments: Segment[] = [];
  // Split on **...** boundaries
  const parts = raw.split(/(\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (part.startsWith('**') && part.endsWith('**')) {
      segments.push({ text: part.slice(2, -2), bold: true });
    } else {
      segments.push({ text: part, bold: false });
    }
  }
  return segments;
}

export default function MarkdownText({ text, style }: Props) {
  if (!text) return null;

  // Split on line breaks first, then parse markdown in each line
  const lines = text.split('\n');

  return (
    <View>
      {lines.map((line, lineIdx) => {
        const segments = parseSegments(line);
        // Render an empty spacer for blank lines
        if (line.trim() === '') {
          return <Text key={lineIdx} style={styles.spacer}>{' '}</Text>;
        }
        return (
          <Text key={lineIdx} style={[styles.line, style]}>
            {segments.map((seg, segIdx) => (
              <Text key={segIdx} style={seg.bold ? styles.bold : undefined}>
                {seg.text}
              </Text>
            ))}
          </Text>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    color: '#ccc',
    fontSize: 14,
    lineHeight: 22,
    marginBottom: 2,
  },
  bold: {
    fontWeight: 'bold',
    color: '#fff',
  },
  spacer: {
    height: 8,
  },
});

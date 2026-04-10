/**
 * MarkdownText — lightweight renderer supporting **bold**, **italic**, bullet points, and \n line breaks.
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
  italic: boolean;
}

function parseSegments(raw: string): Segment[] {
  const segments: Segment[] = [];
  // Split on **...** and *...* boundaries (for bold and italic)
  // More careful regex to avoid matching bullet points (* at start of line)
  const parts = raw.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  for (const part of parts) {
    if (part.startsWith('**') && part.endsWith('**')) {
      // Bold: **text**
      segments.push({ text: part.slice(2, -2), bold: true, italic: false });
    } else if (part.startsWith('*') && part.endsWith('*') && part.length > 2 && !part.startsWith('**')) {
      // Italic: *text*
      segments.push({ text: part.slice(1, -1), bold: false, italic: true });
    } else {
      // Regular text
      if (part) {
        segments.push({ text: part, bold: false, italic: false });
      }
    }
  }
  return segments;
}

export default function MarkdownText({ text, style }: Props) {
  if (!text) return null;

  // Split on line breaks first
  const lines = text.split('\n');

  return (
    <View>
      {lines.map((line, lineIdx) => {
        const trimmed = line.trim();
        
        // Handle bullet points: lines starting with "* " or "- "
        const isBullet = trimmed.startsWith('* ') || trimmed.startsWith('- ');
        const bulletContent = isBullet ? trimmed.slice(2) : trimmed;

        // Render an empty spacer for blank lines
        if (trimmed === '') {
          return <Text key={lineIdx} style={styles.spacer}>{' '}</Text>;
        }

        // Parse markdown segments in the line content
        const segments = parseSegments(bulletContent);

        return (
          <View key={lineIdx} style={isBullet ? styles.bulletLine : undefined}>
            {isBullet ? <Text style={styles.bullet}>• </Text> : null}
            <Text style={[styles.line, style]}>
              {segments.map((seg, segIdx) => (
                <Text
                  key={segIdx}
                  style={[
                    seg.bold && styles.bold,
                    seg.italic && styles.italic,
                  ]}
                >
                  {seg.text}
                </Text>
              ))}
            </Text>
          </View>
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
  italic: {
    fontStyle: 'italic',
    color: '#ddd',
  },
  spacer: {
    height: 8,
  },
  bulletLine: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 4,
  },
  bullet: {
    color: '#e53935',
    fontSize: 14,
    fontWeight: 'bold',
    marginRight: 4,
    lineHeight: 22,
  },
});

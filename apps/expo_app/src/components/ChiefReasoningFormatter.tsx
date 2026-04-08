/**
 * ChiefReasoningFormatter — Parse and display Chief Engineer reasoning in a user-friendly way.
 * Handles JSON objects with reasoning text, converting to readable paragraphs.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import MarkdownText from './MarkdownText';

interface Props {
  reasoning: string;
}

interface ReasoningItem {
  section?: string;
  text: string;
}

/**
 * Try to parse chief reasoning as JSON (with fallback to plain text).
 * Expects either:
 * - { "reasoning_sections": [...], "summary": "..." }
 * - { "items": [{ "section": "...", "text": "..." }, ...] }
 * - Plain text/markdown string
 */
function parseReasoning(raw: string): ReasoningItem[] {
  if (!raw) return [];

  // Try JSON parse first
  try {
    const obj = JSON.parse(raw);
    
    // Case 1: Array of items
    if (Array.isArray(obj)) {
      return obj.map((item) => ({
        section: item.section || item.title || undefined,
        text: item.text || item.content || item.reasoning || String(item),
      }));
    }

    // Case 2: Object with reasoning_sections
    if (obj.reasoning_sections && Array.isArray(obj.reasoning_sections)) {
      const items = obj.reasoning_sections.map((section: any) => ({
        section: section.title || section.section || undefined,
        text: section.text || section.content || section.reasoning || '',
      }));
      if (obj.summary) {
        items.push({ section: 'Resumen', text: obj.summary });
      }
      return items;
    }

    // Case 3: Object with items
    if (obj.items && Array.isArray(obj.items)) {
      return obj.items.map((item: any) => ({
        section: item.section || item.title || undefined,
        text: item.text || item.content || String(item),
      }));
    }

    // Case 4: Object with summary/text
    if (obj.summary || obj.text || obj.reasoning) {
      return [{ text: obj.summary || obj.text || obj.reasoning }];
    }

    // Fallback: treat whole object as single item
    return [{ text: JSON.stringify(obj, null, 2) }];
  } catch (e) {
    // Not JSON, treat as plain text/markdown
    return [{ text: raw }];
  }
}

export default function ChiefReasoningFormatter({ reasoning }: Props) {
  const [expanded, setExpanded] = useState(true);
  const items = parseReasoning(reasoning);

  if (items.length === 0) {
    return <Text style={styles.empty}>Sin razonamiento disponible</Text>;
  }

  return (
    <View>
      <Pressable
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
      >
        <Text style={styles.headerText}>
          {expanded ? '▼' : '▶'} Razonamiento del Ingeniero Jefe
        </Text>
      </Pressable>

      {expanded && (
        <View style={styles.content}>
          {items.map((item, idx) => (
            <View key={idx} style={styles.item}>
              {item.section && (
                <Text style={styles.sectionTitle}>{item.section}</Text>
              )}
              <MarkdownText text={item.text} />
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: '#1a1a3e',
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: '#e53935',
    marginBottom: 8,
  },
  headerText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  content: {
    paddingLeft: 2,
    borderLeftWidth: 2,
    borderLeftColor: '#444',
    paddingVertical: 8,
  },
  item: {
    marginBottom: 12,
    paddingLeft: 12,
  },
  sectionTitle: {
    color: '#e53935',
    fontWeight: 'bold',
    fontSize: 13,
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  empty: {
    color: '#666',
    fontStyle: 'italic',
    fontSize: 14,
  },
});

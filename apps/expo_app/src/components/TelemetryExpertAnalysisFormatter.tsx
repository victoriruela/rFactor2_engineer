import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import MarkdownText from './MarkdownText';

interface Props {
  analysis: string;
}

export default function TelemetryExpertAnalysisFormatter({ analysis }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!analysis || analysis.trim().length === 0) {
    return <Text style={styles.empty}>Sin análisis de expertos de telemetría disponible</Text>;
  }

  return (
    <View>
      <Pressable
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
      >
        <Text style={styles.headerText}>
          {expanded ? '▼' : '▶'} Análisis de Expertos de Telemetría
        </Text>
      </Pressable>
      {expanded ? (
        <View style={styles.content}>
          <MarkdownText text={analysis} />
        </View>
      ) : null}
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
    borderLeftColor: '#42a5f5',
    marginBottom: 8,
  },
  headerText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  content: {
    paddingLeft: 12,
    borderLeftWidth: 2,
    borderLeftColor: '#444',
    paddingVertical: 8,
  },
  empty: {
    color: '#666',
    fontStyle: 'italic',
    fontSize: 14,
  },
});

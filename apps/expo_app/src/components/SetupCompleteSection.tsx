/**
 * SetupCompleteSection — Collapsible view of the complete setup read from SVM file.
 * Groups parameters by section, shows current values only.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import type { SetupChange } from '../api';

interface Props {
  fullSetup: Record<string, SetupChange[]>;
}

export default function SetupCompleteSection({ fullSetup }: Props) {
  const [expanded, setExpanded] = useState(true);
  const sections = Object.entries(fullSetup).filter(([, items]) => items.length > 0);

  if (sections.length === 0) {
    return null;
  }

  return (
    <View style={styles.container}>
      <Pressable
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
      >
        <Text style={styles.headerText}>
          {expanded ? '▼' : '▶'} Setup Actual Completo
        </Text>
      </Pressable>

      {expanded && (
        <View style={styles.content}>
          {sections.map(([section, items]) => (
            <View key={section} style={styles.section}>
              <Text style={styles.sectionName}>{section}</Text>
              <View style={styles.paramsList}>
                {items.map((param, idx) => (
                  <View key={idx} style={styles.paramRow}>
                    <Text style={styles.paramName}>{param.parameter}</Text>
                    <Text style={styles.paramValue}>{param.old_value}</Text>
                  </View>
                ))}
              </View>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginBottom: 16,
  },
  header: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: '#1a1a3e',
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: '#4caf50',
    marginBottom: 8,
  },
  headerText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  content: {
    paddingVertical: 8,
  },
  section: {
    marginBottom: 12,
  },
  sectionName: {
    color: '#4caf50',
    fontWeight: 'bold',
    fontSize: 12,
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  paramsList: {
    paddingLeft: 8,
    borderLeftWidth: 1,
    borderLeftColor: '#444',
  },
  paramRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#222',
  },
  paramName: {
    color: '#aaa',
    fontSize: 12,
    fontWeight: '500',
    flex: 2,
  },
  paramValue: {
    color: '#4caf50',
    fontSize: 12,
    fontWeight: '600',
    flex: 1,
    textAlign: 'right',
  },
});

import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import type { SetupChange } from '../api';

interface Props {
  changes: Record<string, SetupChange[]>;
}

export default function SetupTable({ changes }: Props) {
  const sections = Object.entries(changes).filter(([, v]) => v.length > 0);

  if (sections.length === 0) {
    return <Text style={styles.empty}>Sin cambios recomendados</Text>;
  }

  return (
    <ScrollView horizontal>
      <View>
        {sections.map(([section, items]) => (
          <View key={section} style={styles.section}>
            <Text style={styles.sectionName}>{section}</Text>
            <View style={styles.headerRow}>
              <Text style={[styles.cell, styles.headerCell, { flex: 2 }]}>Parámetro</Text>
              <Text style={[styles.cell, styles.headerCell]}>Actual</Text>
              <Text style={[styles.cell, styles.headerCell]}>Nuevo</Text>
              <Text style={[styles.cell, styles.headerCell]}>%</Text>
              <Text style={[styles.cell, styles.headerCell, { flex: 3 }]}>Razón</Text>
            </View>
            {items.map((change, i) => (
              <View key={i} style={styles.row}>
                <Text style={[styles.cell, { flex: 2 }]}>{change.parameter}</Text>
                <Text style={styles.cell}>{change.old_value}</Text>
                <Text style={[styles.cell, styles.newValue]}>{change.new_value}</Text>
                <Text style={[styles.cell, change.change_pct > 0 ? styles.positive : styles.negative]}>
                  {change.change_pct > 0 ? '+' : ''}{change.change_pct.toFixed(1)}%
                </Text>
                <Text style={[styles.cell, { flex: 3 }]}>{change.reason}</Text>
              </View>
            ))}
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  section: {
    marginBottom: 16,
  },
  sectionName: {
    color: '#e53935',
    fontWeight: 'bold',
    fontSize: 14,
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  headerRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#444',
    paddingBottom: 4,
    marginBottom: 4,
  },
  row: {
    flexDirection: 'row',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#222',
  },
  cell: {
    flex: 1,
    color: '#ccc',
    fontSize: 12,
    paddingHorizontal: 4,
    minWidth: 80,
  },
  headerCell: {
    color: '#888',
    fontWeight: 'bold',
    textTransform: 'uppercase',
    fontSize: 11,
  },
  newValue: {
    color: '#4caf50',
    fontWeight: '600',
  },
  positive: {
    color: '#4caf50',
  },
  negative: {
    color: '#f44336',
  },
  empty: {
    color: '#666',
    fontStyle: 'italic',
  },
});

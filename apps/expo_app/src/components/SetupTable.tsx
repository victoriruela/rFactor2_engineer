import React from 'react';
import { View, Text, StyleSheet, Dimensions } from 'react-native';
import type { SetupChange } from '../api';

interface Props {
  changes: Record<string, SetupChange[]>;
}

export default function SetupTable({ changes }: Props) {
  const sections = Object.entries(changes).filter(([, v]) => v.length > 0);
  const isSmallScreen = Dimensions.get('window').width < 600;

  if (sections.length === 0) {
    return <Text style={styles.empty}>Sin cambios recomendados</Text>;
  }

  return (
    <View>
      {sections.map(([section, items]) => (
        <View key={section} style={styles.section}>
          <Text style={styles.sectionName}>{section}</Text>
          
          {!isSmallScreen ? (
            // Desktop: table layout with horizontal scroll capability
            <View style={styles.tableContainer}>
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
                  <Text style={[styles.cell, change.change_pct?.startsWith('+') ? styles.positive : styles.negative]}>
                    {change.change_pct || '—'}
                  </Text>
                  <Text style={[styles.cell, { flex: 3 }]}>{change.reason}</Text>
                </View>
              ))}
            </View>
          ) : (
            // Mobile: card-style layout
            <View style={styles.cardContainer}>
              {items.map((change, i) => (
                <View key={i} style={styles.card}>
                  <View style={styles.cardRow}>
                    <Text style={styles.cardLabel}>Parámetro:</Text>
                    <Text style={styles.cardValue}>{change.parameter}</Text>
                  </View>
                  <View style={styles.cardRow}>
                    <Text style={styles.cardLabel}>Actual:</Text>
                    <Text style={styles.cardValue}>{change.old_value}</Text>
                  </View>
                  <View style={styles.cardRow}>
                    <Text style={styles.cardLabel}>Nuevo:</Text>
                    <Text style={[styles.cardValue, styles.newValue]}>{change.new_value}</Text>
                  </View>
                  {change.change_pct && (
                    <View style={styles.cardRow}>
                      <Text style={styles.cardLabel}>Cambio:</Text>
                      <Text style={[styles.cardValue, change.change_pct?.startsWith('+') ? styles.positive : styles.negative]}>
                        {change.change_pct}
                      </Text>
                    </View>
                  )}
                  <View style={styles.cardRowReason}>
                    <Text style={styles.cardLabel}>Razón:</Text>
                    <Text style={styles.cardValueReason}>{change.reason}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    marginBottom: 20,
  },
  sectionName: {
    color: '#e53935',
    fontWeight: 'bold',
    fontSize: 14,
    marginBottom: 10,
    textTransform: 'uppercase',
  },
  empty: {
    color: '#666',
    fontStyle: 'italic',
  },
  // Desktop table styles
  tableContainer: {
    borderRadius: 6,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#333',
  },
  headerRow: {
    flexDirection: 'row',
    backgroundColor: '#0d0d1f',
    borderBottomWidth: 1,
    borderBottomColor: '#444',
  },
  row: {
    flexDirection: 'row',
    paddingVertical: 6,
    paddingHorizontal: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#222',
    backgroundColor: '#0f0f23',
  },
  cell: {
    flex: 1,
    color: '#ccc',
    fontSize: 12,
    paddingHorizontal: 4,
    minWidth: 70,
  },
  headerCell: {
    color: '#888',
    fontWeight: 'bold',
    textTransform: 'uppercase',
    fontSize: 11,
    paddingVertical: 8,
  },
  // Mobile card styles
  cardContainer: {
    gap: 10,
  },
  card: {
    backgroundColor: '#0d0d1f',
    borderRadius: 6,
    padding: 10,
    borderLeftWidth: 3,
    borderLeftColor: '#e53935',
    gap: 6,
  },
  cardRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 2,
  },
  cardRowReason: {
    flexDirection: 'column',
    paddingVertical: 4,
    paddingTopToLargeWidth: 8,
  },
  cardLabel: {
    color: '#888',
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    minWidth: 60,
  },
  cardValue: {
    color: '#ccc',
    fontSize: 12,
    fontWeight: '500',
    flex: 1,
    textAlign: 'right',
  },
  cardValueReason: {
    color: '#aaa',
    fontSize: 12,
    marginTop: 4,
    lineHeight: 18,
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
});

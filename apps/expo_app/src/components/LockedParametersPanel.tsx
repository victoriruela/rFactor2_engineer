/**
 * LockedParametersPanel — UI to mark/unmark setup parameters as "locked" (fixed).
 * Locked parameters won't get change recommendations from AI.
 * Shows only currently locked parameters and allows unlocking.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useAppStore } from '../store/useAppStore';
import type { SetupChange } from '../api';
import { getClicksDisplay, getValueDisplay } from '../utils/setupValueParser';
import { toSpanishParameterName, toSpanishSectionName } from '../utils/labelTranslator';

interface Props {
  fullSetup: Record<string, SetupChange[]>;
  onLocked?: (params: Set<string>) => void;
}

export default function LockedParametersPanel({ fullSetup, onLocked }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { lockedParameters, toggleLockedParameter } = useAppStore();

  const sections = Object.entries(fullSetup)
    .map(([section, items]) => [section, items.filter((item) => lockedParameters.has(item.parameter))] as const)
    .filter(([, items]) => items.length > 0);
  const lockedCount = sections.reduce((acc, [, items]) => acc + items.length, 0);

  const handleToggle = (param: string) => {
    toggleLockedParameter(param);
    onLocked?.(lockedParameters);
  };

  return (
    <View style={styles.container}>
      <Pressable
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
      >
        <Text style={styles.headerText}>
          {expanded ? '▼' : '▶'} Parámetros Fijados ({lockedCount})
        </Text>
      </Pressable>
      {expanded ? (
        <View style={styles.content}>
          {sections.length === 0 ? (
            <View style={styles.emptyBox}>
              <Text style={styles.emptyText}>No hay parámetros fijados todavía.</Text>
            </View>
          ) : (
            <>
              {sections.map(([section, items]) => (
                <View key={section} style={styles.section}>
                  <Text style={styles.sectionName}>{toSpanishSectionName(section)}</Text>
                  <View style={styles.paramsList}>
                    {items.map((param, idx) => {
                      const clicks = getClicksDisplay(param.old_value);
                      const valueDisplay = getValueDisplay(param.old_value);
                      return (
                        <Pressable
                          key={`${section}-${param.parameter}-${idx}`}
                          style={styles.paramRow}
                          onPress={() => handleToggle(param.parameter)}
                        >
                          <View style={styles.paramInfo}>
                            <Text style={styles.paramName}>{toSpanishParameterName(param.parameter)}</Text>
                            <View style={styles.paramDetailsRow}>
                              <Text style={[styles.paramDetail, styles.clicksDetail]}>{clicks}</Text>
                              <Text style={styles.paramValue}>{valueDisplay}</Text>
                            </View>
                          </View>
                          <Text style={styles.lockIcon}>🔒</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </View>
              ))}
              <View style={styles.hint}>
                <Text style={styles.hintText}>
                  Haz clic en un parámetro fijado para devolverlo a Setup Actual Completo.
                </Text>
              </View>
            </>
          )}
        </View>
      ) : null}
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
    borderLeftColor: '#ff9800',
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
  emptyBox: {
    backgroundColor: '#0d0d1f',
    borderRadius: 6,
    padding: 10,
    borderLeftWidth: 2,
    borderLeftColor: '#ff9800',
  },
  emptyText: {
    color: '#ccc',
    fontSize: 12,
    fontStyle: 'italic',
  },
  section: {
    marginBottom: 12,
  },
  sectionName: {
    color: '#ff9800',
    fontWeight: 'bold',
    fontSize: 12,
    marginBottom: 8,
    textTransform: 'uppercase',
    paddingHorizontal: 4,
  },
  paramsList: {
    paddingLeft: 4,
    borderLeftWidth: 2,
    borderLeftColor: '#444',
    gap: 4,
  },
  paramRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 8,
    marginHorizontal: 4,
    borderRadius: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#222',
    backgroundColor: '#0d0d1f',
  },
  paramInfo: {
    flex: 1,
    gap: 4,
  },
  paramName: {
    color: '#ccc',
    fontSize: 13,
    fontWeight: '500',
  },
  paramDetailsRow: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
  },
  paramDetail: {
    fontSize: 11,
    fontStyle: 'italic',
  },
  clicksDetail: {
    color: '#66bb6a',
    fontWeight: '600',
    minWidth: 40,
  },
  paramValue: {
    color: '#888',
    fontSize: 11,
    fontStyle: 'italic',
    flex: 1,
  },
  lockIcon: {
    fontSize: 14,
    marginLeft: 8,
    minWidth: 24,
    textAlign: 'center',
  },
  hint: {
    marginTop: 12,
    paddingVertical: 8,
    paddingHorizontal: 10,
    backgroundColor: '#0a0a15',
    borderRadius: 4,
    borderLeftWidth: 2,
    borderLeftColor: '#ff9800',
  },
  hintText: {
    color: '#ff9800',
    fontSize: 11,
    fontStyle: 'italic',
    lineHeight: 16,
  },
});

/**
 * SetupCompleteSection — Collapsible view of the complete setup read from SVM file.
 * Groups parameters by section, shows current values only.
 * Allows marking parameters as "locked" (fixed) - the AI won't suggest changes for them.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useAppStore } from '../store/useAppStore';
import type { SetupChange } from '../api';

interface Props {
  fullSetup: Record<string, SetupChange[]>;
}

export default function SetupCompleteSection({ fullSetup }: Props) {
  const [expanded, setExpanded] = useState(true);
  const { lockedParameters, toggleLockedParameter } = useAppStore();
  const sections = Object.entries(fullSetup).filter(([, items]) => items.length > 0);

  if (sections.length === 0) {
    return null;
  }

  const handleToggleLock = (param: string) => {
    toggleLockedParameter(param);
  };

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
                {items.map((param, idx) => {
                  const isLocked = lockedParameters.has(param.parameter);
                  return (
                    <Pressable
                      key={idx}
                      style={[styles.paramRow, isLocked && styles.paramRowLocked]}
                      onPress={() => handleToggleLock(param.parameter)}
                    >
                      <View style={styles.paramInfo}>
                        <Text style={styles.paramName}>{param.parameter}</Text>
                        <Text style={styles.paramValue}>{param.old_value}</Text>
                      </View>
                      <Text style={[styles.lockIcon, isLocked && styles.lockIconActive]}>
                        {isLocked ? '🔒' : '⭕'}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          ))}
          
          <View style={styles.hint}>
            <Text style={styles.hintText}>
              Haz clic en un parámetro para marcarlo como 🔒 fijado (la IA no lo cambiará)
            </Text>
          </View>
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
  paramRowLocked: {
    backgroundColor: '#1a1f2e',
    borderBottomColor: '#4caf50',
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
  paramValue: {
    color: '#888',
    fontSize: 11,
    fontStyle: 'italic',
  },
  lockIcon: {
    fontSize: 14,
    marginLeft: 8,
    minWidth: 24,
    textAlign: 'center',
  },
  lockIconActive: {
    opacity: 1,
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

/**
 * LockedParametersPanel — UI to mark/unmark setup parameters as "locked" (fixed).
 * Locked parameters won't get change recommendations from AI.
 * Shows which parameters are currently locked and allows toggling.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView } from 'react-native';
import { useAppStore } from '../store/useAppStore';
import type { SetupChange } from '../api';

interface Props {
  fullSetup: Record<string, SetupChange[]>;
  onLocked?: (params: Set<string>) => void;
}

export default function LockedParametersPanel({ fullSetup, onLocked }: Props) {
  const [expanded, setExpanded] = useState(true);
  const { lockedParameters, toggleLockedParameter } = useAppStore();

  // Flatten all parameters from all sections
  const allParams = Object.values(fullSetup)
    .flat()
    .map((p) => p.parameter)
    .sort();

  const uniqueParams = Array.from(new Set(allParams));
  const lockedCount = uniqueParams.filter((p) => lockedParameters.has(p)).length;

  const handleToggle = (param: string) => {
    toggleLockedParameter(param);
    onLocked?.(lockedParameters);
  };

  if (uniqueParams.length === 0) {
    return null;
  }

  return (
    <View style={styles.container}>
      <Pressable
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
      >
        <Text style={styles.headerText}>
          {expanded ? '▼' : '▶'} Parámetros Fijados ({lockedCount}/{uniqueParams.length})
        </Text>
      </Pressable>

      {expanded && (
        <View style={styles.content}>
          {lockedCount > 0 && (
            <View style={styles.lockedSummary}>
              <Text style={styles.summaryLabel}>Parámetros fijados:</Text>
              <Text style={styles.lockedList}>
                {uniqueParams.filter((p) => lockedParameters.has(p)).join(', ')}
              </Text>
            </View>
          )}

          <Text style={styles.instruction}>
            Haz clic en los parámetros que no deseas que el IA cambie:
          </Text>

          <ScrollView
            horizontal
            contentContainerStyle={styles.paramGrid}
            showsHorizontalScrollIndicator={false}
          >
            {uniqueParams.map((param) => {
              const isLocked = lockedParameters.has(param);
              return (
                <Pressable
                  key={param}
                  style={[styles.paramChip, isLocked && styles.paramChipLocked]}
                  onPress={() => handleToggle(param)}
                >
                  <Text style={[styles.paramText, isLocked && styles.paramTextLocked]}>
                    {isLocked ? '🔒 ' : ''}
                    {param}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
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
    borderLeftColor: '#ff9800',
    marginBottom: 8,
  },
  headerText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  content: {
    paddingVertical: 12,
    paddingHorizontal: 8,
  },
  lockedSummary: {
    backgroundColor: '#0d0d1f',
    borderRadius: 6,
    padding: 8,
    marginBottom: 12,
    borderLeftWidth: 2,
    borderLeftColor: '#ff9800',
  },
  summaryLabel: {
    color: '#ff9800',
    fontWeight: 'bold',
    fontSize: 12,
    marginBottom: 4,
  },
  lockedList: {
    color: '#ccc',
    fontSize: 12,
    lineHeight: 18,
  },
  instruction: {
    color: '#888',
    fontSize: 12,
    marginBottom: 8,
    fontStyle: 'italic',
  },
  paramGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  paramChip: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 4,
    backgroundColor: '#222',
    borderWidth: 1,
    borderColor: '#444',
    marginBottom: 6,
  },
  paramChipLocked: {
    backgroundColor: '#ff9800',
    borderColor: '#ff9800',
  },
  paramText: {
    color: '#aaa',
    fontSize: 12,
    fontWeight: '500',
  },
  paramTextLocked: {
    color: '#000',
    fontWeight: '600',
  },
});

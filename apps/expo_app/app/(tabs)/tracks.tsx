import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, FlatList, ActivityIndicator } from 'react-native';
import { listTracks, type TrackInfo } from '../../src/api';
import { useAppStore } from '../../src/store/useAppStore';

export default function TracksScreen() {
  const { tracks, setTracks } = useAppStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listTracks()
      .then(setTracks)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [setTracks]);

  const renderItem = ({ item }: { item: TrackInfo }) => (
    <View style={styles.card}>
      <Text style={styles.name}>{item.name}</Text>
      <View style={styles.details}>
        <Text style={styles.detail}>📍 {item.country}</Text>
        <Text style={styles.detail}>📏 {item.length_km} km</Text>
        <Text style={styles.detail}>↩️ {item.turns} curvas</Text>
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Circuitos</Text>
      {loading ? (
        <ActivityIndicator size="large" color="#e53935" />
      ) : (
        <FlatList
          data={tracks}
          keyExtractor={(t) => t.id}
          renderItem={renderItem}
          contentContainerStyle={{ paddingBottom: 24 }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
    padding: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 16,
  },
  card: {
    backgroundColor: '#1a1a3e',
    padding: 16,
    borderRadius: 8,
    marginBottom: 12,
  },
  name: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 16,
    marginBottom: 8,
  },
  details: {
    flexDirection: 'row',
    gap: 16,
  },
  detail: {
    color: '#aaa',
    fontSize: 13,
  },
});

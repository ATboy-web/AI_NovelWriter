/**
 * 章节编辑页
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../styles/theme';

export default function ChapterScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>章节编辑页</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bgDark, alignItems: 'center', justifyContent: 'center' },
  text: { color: COLORS.textPrimary, fontSize: 18 },
});

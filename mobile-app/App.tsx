/**
 * AI小说创作工坊 - 移动版主应用
 */

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

// 导入页面
import HomeScreen from './src/screens/HomeScreen';
import EditorScreen from './src/screens/EditorScreen';
import LibraryScreen from './src/screens/LibraryScreen';
import ToolsScreen from './src/screens/ToolsScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import NovelDetailScreen from './src/screens/NovelDetailScreen';
import ChapterScreen from './src/screens/ChapterScreen';
import ToolDetailScreen from './src/screens/ToolDetailScreen';

// 导入主题
import { COLORS } from './src/styles/theme';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

// 底部标签导航
function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName: keyof typeof Ionicons.glyphMap = 'home';
          
          if (route.name === '首页') {
            iconName = focused ? 'home' : 'home-outline';
          } else if (route.name === '书架') {
            iconName = focused ? 'library' : 'library-outline';
          } else if (route.name === '写作') {
            iconName = focused ? 'create' : 'create-outline';
          } else if (route.name === '工具') {
            iconName = focused ? 'build' : 'build-outline';
          } else if (route.name === '我的') {
            iconName = focused ? 'person' : 'person-outline';
          }
          
          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: COLORS.accent,
        tabBarInactiveTintColor: COLORS.textMuted,
        tabBarStyle: {
          backgroundColor: COLORS.bgMedium,
          borderTopColor: COLORS.border,
          paddingBottom: 5,
          height: 60,
        },
        tabBarLabelStyle: {
          fontSize: 12,
          marginBottom: 5,
        },
        headerStyle: {
          backgroundColor: COLORS.bgDark,
        },
        headerTintColor: COLORS.textPrimary,
        headerTitleStyle: {
          fontWeight: 'bold',
        },
      })}
    >
      <Tab.Screen name="首页" component={HomeScreen} />
      <Tab.Screen name="书架" component={LibraryScreen} />
      <Tab.Screen name="写作" component={EditorScreen} />
      <Tab.Screen name="工具" component={ToolsScreen} />
      <Tab.Screen name="我的" component={SettingsScreen} />
    </Tab.Navigator>
  );
}

// 主导航
export default function App() {
  return (
    <SafeAreaProvider>
      <NavigationContainer
        theme={{
          dark: true,
          colors: {
            primary: COLORS.accent,
            background: COLORS.bgDark,
            card: COLORS.bgMedium,
            text: COLORS.textPrimary,
            border: COLORS.border,
            notification: COLORS.accent,
          },
        }}
      >
        <Stack.Navigator
          screenOptions={{
            headerStyle: { backgroundColor: COLORS.bgDark },
            headerTintColor: COLORS.textPrimary,
            headerTitleStyle: { fontWeight: 'bold' },
          }}
        >
          <Stack.Screen 
            name="MainTabs" 
            component={MainTabs} 
            options={{ headerShown: false }}
          />
          <Stack.Screen 
            name="NovelDetail" 
            component={NovelDetailScreen}
            options={{ title: '小说详情' }}
          />
          <Stack.Screen 
            name="Chapter" 
            component={ChapterScreen}
            options={{ title: '章节编辑' }}
          />
          <Stack.Screen 
            name="ToolDetail" 
            component={ToolDetailScreen}
            options={({ route }: any) => ({ 
              title: route.params?.toolId ? '工具详情' : '工具' 
            })}
          />
        </Stack.Navigator>
        <StatusBar style="light" />
      </NavigationContainer>
    </SafeAreaProvider>
  );
}

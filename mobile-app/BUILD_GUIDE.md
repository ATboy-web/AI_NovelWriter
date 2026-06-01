# Android APK 构建指南

## 方案一：Expo云构建（推荐，最简单）

### 步骤

1. **注册Expo账号**
   - 访问 https://expo.dev/signup
   - 注册免费账号

2. **安装EAS CLI**
   ```bash
   npm install -g eas-cli
   ```

3. **登录**
   ```bash
   eas login
   ```

4. **构建APK**
   ```bash
   cd ai-novel-writer/mobile-app
   eas build --platform android --profile preview
   ```

5. **下载APK**
   - 构建完成后会提供下载链接
   - 或在 https://expo.dev 控制台下载

---

## 方案二：本地构建（需要Android SDK）

### 环境要求

1. **安装JDK 17**
   ```bash
   # Windows (使用winget)
   winget install EclipseAdoptium.Temurin.17.JDK
   
   # 或下载: https://adoptium.net/
   ```

2. **安装Android Studio**
   - 下载: https://developer.android.com/studio
   - 安装时勾选 Android SDK

3. **设置环境变量**
   ```bash
   # Windows
   set ANDROID_HOME=C:\Users\%USERNAME%\AppData\Local\Android\Sdk
   set PATH=%PATH%;%ANDROID_HOME%\platform-tools;%ANDROID_HOME%\tools
   ```

### 构建步骤

```bash
cd ai-novel-writer/mobile-app

# 安装依赖
npm install

# 生成Android项目
npx expo prebuild --platform android

# 进入Android目录
cd android

# 构建APK
./gradlew assembleRelease

# APK位置
# android/app/build/outputs/apk/release/app-release.apk
```

---

## 方案三：使用Expo Go测试（无需构建）

### 步骤

1. **手机安装Expo Go**
   - Android: https://play.google.com/store/apps/details?id=host.exp.exponent
   - iOS: https://apps.apple.com/app/expo-go/id982107779

2. **启动开发服务器**
   ```bash
   cd ai-novel-writer/mobile-app
   npm install
   npx expo start
   ```

3. **扫码连接**
   - 终端会显示二维码
   - 用Expo Go扫描即可在手机上运行

---

## 方案四：使用PWA（无需安装）

将应用配置为PWA，手机浏览器直接访问：

1. **启动Web版本**
   ```bash
   cd ai-novel-writer/mobile-app
   npx expo start --web
   ```

2. **手机访问**
   - 确保手机和电脑在同一网络
   - 手机浏览器访问 `http://电脑IP:19006`
   - 添加到主屏幕即可像App一样使用

---

## 连接桌面版

无论使用哪种方案，都需要连接桌面版AI服务：

1. **启动桌面版**
   - 运行 `AI_NovelWriter.exe`

2. **获取电脑IP**
   ```bash
   # Windows
   ipconfig
   # 找到 IPv4 地址，如 192.168.1.100
   ```

3. **手机配置**
   - 打开App → 设置 → API地址
   - 输入 `http://你的电脑IP:8001`
   - 如 `http://192.168.1.100:8001`

4. **测试连接**
   - 点击"测试连接"
   - 显示"连接成功"即可使用

---

## 常见问题

### Q: 构建失败怎么办？
A: 检查JDK和Android SDK是否正确安装，环境变量是否设置。

### Q: 手机连不上API？
A: 确保手机和电脑在同一WiFi网络，关闭电脑防火墙。

### Q: APK安装失败？
A: 手机设置中开启"允许安装未知来源应用"。

### Q: 如何更新App？
A: 重新构建APK并安装，或使用Expo Go实时更新。

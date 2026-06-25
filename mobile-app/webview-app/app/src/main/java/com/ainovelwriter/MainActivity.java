package com.ainovelwriter;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.graphics.Bitmap;
import android.widget.Toast;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.FileReader;

public class MainActivity extends Activity {
    private static final String TAG = "AINovelWriter";
    private WebView webView;
    private File novelsDir;
    private PowerManager.WakeLock wakeLock;
    private KeepAliveService keepAliveService;
    private boolean serviceBound = false;
    
    // 共享OkHttpClient单例（连接池复用）
    private static final okhttp3.OkHttpClient httpClient = new okhttp3.OkHttpClient.Builder()
        .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(300, java.util.concurrent.TimeUnit.SECONDS)  // 5分钟读取超时（长章节生成需要）
        .writeTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build();

    private ServiceConnection serviceConnection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder service) {
            KeepAliveService.LocalBinder binder = (KeepAliveService.LocalBinder) service;
            keepAliveService = binder.getService();
            serviceBound = true;
            Log.d(TAG, "KeepAlive service connected");
        }

        @Override
        public void onServiceDisconnected(ComponentName name) {
            keepAliveService = null;
            serviceBound = false;
            Log.d(TAG, "KeepAlive service disconnected");
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        try {
            // Fullscreen
            requestWindowFeature(Window.FEATURE_NO_TITLE);
            getWindow().setFlags(
                WindowManager.LayoutParams.FLAG_FULLSCREEN,
                WindowManager.LayoutParams.FLAG_FULLSCREEN
            );

            // Keep screen on
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

            // Initialize novels directory (外部存储不可用时回退到内部存储)
            File externalDir = getExternalFilesDir(null);
            if (externalDir == null) {
                externalDir = getFilesDir();
            }
            novelsDir = new File(externalDir, "AI_NovelWriter");
            if (!novelsDir.exists()) {
                novelsDir.mkdirs();
            }

            // Initialize wake lock
            try {
                PowerManager powerManager = (PowerManager) getSystemService(POWER_SERVICE);
                if (powerManager != null) {
                    wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AINovelWriter::WakeLock");
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to init wake lock: " + e.getMessage());
            }

            // Start and bind keep-alive service
            startKeepAliveService();

            webView = new WebView(this);
            setContentView(webView);

            // Configure WebView
            WebSettings settings = webView.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setAllowFileAccess(true);
            settings.setAllowContentAccess(true);
            settings.setAllowFileAccessFromFileURLs(false);  // 安全：禁止跨文件访问
            settings.setAllowUniversalAccessFromFileURLs(false);  // 安全：禁止通用访问
            settings.setDatabaseEnabled(true);
            settings.setCacheMode(WebSettings.LOAD_DEFAULT);
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
            settings.setMediaPlaybackRequiresUserGesture(false);
            settings.setLoadWithOverviewMode(true);
            settings.setUseWideViewPort(true);
            settings.setBuiltInZoomControls(false);
            settings.setSupportZoom(false);
            settings.setBlockNetworkImage(false);
            settings.setBlockNetworkLoads(false);
            webView.setBackgroundColor(0xFF1a1a2e);

            // Disable debugging in production
            WebView.setWebContentsDebuggingEnabled(false); // Release mode: disable debugging

            // Add JavascriptInterface
            webView.addJavascriptInterface(new NovelFileInterface(), "NovelFS");

            // Set WebView client
            webView.setWebViewClient(new WebViewClient() {
                @Override
                public boolean shouldOverrideUrlLoading(WebView view, String url) {
                    // 只允许本地asset文件和data URL
                    if (url.startsWith("file:///android_asset/") || url.startsWith("data:")) {
                        return false;
                    }
                    // 阻止所有其他URL（包括javascript:、http://、https://等）
                    return true;
                }

                @Override
                public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                    Log.e(TAG, "Resource error: " + error.getDescription());
                }
            });

            webView.setWebChromeClient(new WebChromeClient() {
                @Override
                public boolean onConsoleMessage(ConsoleMessage consoleMessage) {
                    Log.d(TAG, "JS [" + consoleMessage.messageLevel() + "] " + consoleMessage.message());
                    return true;
                }
            });

            Log.d(TAG, "Loading index.html");
            webView.loadUrl("file:///android_asset/index.html");
            
        } catch (Exception e) {
            Log.e(TAG, "Fatal error in onCreate: " + e.getMessage(), e);
            Toast.makeText(this, "启动失败: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void startKeepAliveService() {
        try {
            Intent serviceIntent = new Intent(this, KeepAliveService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
            bindService(serviceIntent, serviceConnection, Context.BIND_AUTO_CREATE);
            Log.d(TAG, "KeepAlive service started");
        } catch (Exception e) {
            Log.e(TAG, "Failed to start keep-alive service: " + e.getMessage());
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            moveTaskToBack(true);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (webView != null) {
            webView.onPause();
            webView.pauseTimers();  // 暂停JS定时器，省电
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
            webView.resumeTimers();
        }
    }

    @Override
    protected void onDestroy() {
        try {
            // Release wake lock
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
            
            // Unbind service
            if (serviceBound) {
                unbindService(serviceConnection);
                serviceBound = false;
            }
        } catch (Exception e) {
            Log.e(TAG, "Error in onDestroy: " + e.getMessage());
        }
        
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    /**
     * Keep-Alive Foreground Service
     */
    public static class KeepAliveService extends Service {
        private static final String CHANNEL_ID = "AINovelWriter_Channel";
        private static final int NOTIFICATION_ID = 1001;
        private final IBinder binder = new LocalBinder();

        public class LocalBinder extends android.os.Binder {
            public KeepAliveService getService() {
                return KeepAliveService.this;
            }
        }

        @Override
        public void onCreate() {
            super.onCreate();
            createNotificationChannel();
            try {
                startForeground(NOTIFICATION_ID, createNotification());
                Log.d(TAG, "KeepAlive service foreground started");
            } catch (Exception e) {
                Log.e(TAG, "Failed to start foreground: " + e.getMessage());
            }
        }

        @Override
        public int onStartCommand(Intent intent, int flags, int startId) {
            return START_STICKY; // Restart if killed
        }

        @Override
        public IBinder onBind(Intent intent) {
            return binder;
        }

        private void createNotificationChannel() {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "AI小说创作工坊",
                    NotificationManager.IMPORTANCE_LOW
                );
                channel.setDescription("保持应用在后台运行");
                channel.setShowBadge(false);
                
                NotificationManager manager = getSystemService(NotificationManager.class);
                if (manager != null) {
                    manager.createNotificationChannel(channel);
                }
            }
        }

        private Notification createNotification() {
            Intent notificationIntent = new Intent(this, MainActivity.class);
            notificationIntent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent pendingIntent = PendingIntent.getActivity(
                this, 0, notificationIntent, 
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
            );

            Notification.Builder builder;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                builder = new Notification.Builder(this, CHANNEL_ID);
            } else {
                builder = new Notification.Builder(this);
            }

            return builder
                .setContentTitle("AI小说创作工坊")
                .setContentText("正在创作中... 点击返回应用")
                .setSmallIcon(android.R.drawable.ic_menu_edit)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .build();
        }

        @Override
        public void onDestroy() {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) {
                stopForeground(true);
            }
            super.onDestroy();
            Log.d(TAG, "KeepAlive service destroyed");
        }
    }

    /**
     * JavascriptInterface
     */
    public class NovelFileInterface {
        private volatile String lastResponse = null;
        private volatile String lastError = null;
        private volatile int lastStatusCode = 0;
        private volatile boolean requestComplete = false;
        private volatile Exception lastException = null;
        private final Object fileLock = new Object();  // 文件操作锁
        
        /**
         * Validate and sanitize path to prevent path traversal
         */
        private File getSafeFile(String novelName, String relativePath) {
            try {
                // Remove path traversal attempts
                String safeName = novelName.replaceAll("[\\\\/]", "_").replaceAll("\\.\\.", "");
                String safePath = relativePath.replaceAll("\\\\", "/").replaceAll("\\.\\.", "");
                
                File file = new File(novelsDir, safeName + "/" + safePath);
                String canonicalPath = file.getCanonicalPath();
                String novelsDirPath = novelsDir.getCanonicalPath();
                
                // Ensure file is within novels directory
                if (!canonicalPath.startsWith(novelsDirPath)) {
                    Log.e(TAG, "Path traversal attempt blocked: " + relativePath);
                    return null;
                }
                
                return file;
            } catch (Exception e) {
                Log.e(TAG, "Path validation failed: " + e.getMessage());
                return null;
            }
        }
        
        @JavascriptInterface
        public String getNovelsDir() {
            return novelsDir != null ? novelsDir.getAbsolutePath() : "";
        }
        
        @JavascriptInterface
        public boolean createNovelDir(String novelName) {
            try {
                File novelDir = getSafeFile(novelName, "");
                if (novelDir == null) return false;
                
                if (!novelDir.exists()) {
                    novelDir.mkdirs();
                }
                
                new File(novelDir, "chapters").mkdirs();
                new File(novelDir, "characters").mkdirs();
                new File(novelDir, "outlines").mkdirs();
                new File(novelDir, "memory").mkdirs();
                new File(novelDir, "memory/arcs").mkdirs();
                new File(novelDir, "memory/chapters").mkdirs();
                new File(novelDir, "memory/chunks").mkdirs();
                new File(novelDir, "memory/timeline").mkdirs();
                new File(novelDir, "memory/volumes").mkdirs();
                new File(novelDir, "backups").mkdirs();
                new File(novelDir, "summaries").mkdirs();
                new File(novelDir, "notes").mkdirs();
                new File(novelDir, "scene_prompts").mkdirs();
                new File(novelDir, "images").mkdirs();
                new File(novelDir, "timelines").mkdirs();
                
                return true;
            } catch (Exception e) {
                Log.e(TAG, "Failed to create novel dir: " + e.getMessage());
                return false;
            }
        }
        
        @JavascriptInterface
        public boolean writeFile(String novelName, String relativePath, String content) {
            synchronized (fileLock) {
                try {
                    File file = getSafeFile(novelName, relativePath);
                    if (file == null) return false;

                    File parentDir = file.getParentFile();
                    if (parentDir != null && !parentDir.exists()) {
                        parentDir.mkdirs();
                    }
                    try (FileWriter writer = new FileWriter(file)) {
                        writer.write(content);
                        writer.flush();
                    }
                    return true;
                } catch (IOException e) {
                    Log.e(TAG, "Failed to write file: " + e.getMessage());
                    return false;
                }
            }
        }
        
        @JavascriptInterface
        public String readFile(String novelName, String relativePath) {
            try {
                File file = getSafeFile(novelName, relativePath);
                if (file == null || !file.exists()) {
                    return null;
                }
                StringBuilder sb = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
                    String line;
                    boolean first = true;
                    while ((line = reader.readLine()) != null) {
                        if (!first) sb.append("\n");
                        sb.append(line);
                        first = false;
                    }
                }
                return sb.toString();
            } catch (IOException e) {
                Log.e(TAG, "Failed to read file: " + e.getMessage());
                return null;
            }
        }
        
        @JavascriptInterface
        public boolean fileExists(String novelName, String relativePath) {
            File file = getSafeFile(novelName, relativePath);
            return file != null && file.exists();
        }
        
        @JavascriptInterface
        public String[] listFiles(String novelName, String relativePath) {
            try {
                File dir = getSafeFile(novelName, relativePath);
                if (dir == null || !dir.exists() || !dir.isDirectory()) {
                    return new String[0];
                }
                return dir.list();
            } catch (Exception e) {
                Log.e(TAG, "Failed to list files: " + e.getMessage());
                return new String[0];
            }
        }
        
        @JavascriptInterface
        public boolean deleteFile(String novelName, String relativePath) {
            try {
                File file = getSafeFile(novelName, relativePath);
                return file != null && file.exists() && file.delete();
            } catch (Exception e) {
                Log.e(TAG, "Failed to delete file: " + e.getMessage());
                return false;
            }
        }
        
        @JavascriptInterface
        public String[] listNovels() {
            try {
                if (novelsDir == null || !novelsDir.exists()) {
                    return new String[0];
                }
                return novelsDir.list();
            } catch (Exception e) {
                Log.e(TAG, "Failed to list novels: " + e.getMessage());
                return new String[0];
            }
        }
        
        @JavascriptInterface
        public boolean deleteNovel(String novelName) {
            try {
                File novelDir = getSafeFile(novelName, "");  // 安全：使用路径校验
                if (novelDir == null) return false;
                return deleteRecursive(novelDir);
            } catch (Exception e) {
                Log.e(TAG, "Failed to delete novel: " + e.getMessage());
                return false;
            }
        }
        
        private boolean deleteRecursive(File fileOrDirectory) {
            if (fileOrDirectory.isDirectory()) {
                File[] children = fileOrDirectory.listFiles();
                if (children != null) {
                    for (File child : children) {
                        deleteRecursive(child);
                    }
                }
            }
            return fileOrDirectory.delete();
        }
        
        @JavascriptInterface
        public void showToast(String message) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
        }
        
        @JavascriptInterface
        public void acquireWakeLock() {
            try {
                if (wakeLock != null && !wakeLock.isHeld()) {
                    wakeLock.acquire(30 * 60 * 1000L); // 30 minutes
                    Log.d(TAG, "Wake lock acquired (30min)");
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to acquire wake lock: " + e.getMessage());
            }
        }
        
        @JavascriptInterface
        public void releaseWakeLock() {
            try {
                if (wakeLock != null && wakeLock.isHeld()) {
                    wakeLock.release();
                    Log.d(TAG, "Wake lock released");
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to release wake lock: " + e.getMessage());
            }
        }
        
        @JavascriptInterface
        public void keepAlive() {
            // Called from JS to keep service alive
            Log.d(TAG, "KeepAlive called from JS");
        }
        
        /**
         * Test network connectivity to API endpoint
         * Returns: "OK:statusCode" or "ERROR:message"
         */
        @JavascriptInterface
        public String testConnection(String urlStr) {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(urlStr);
                conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(8000);  // 8s
                conn.setReadTimeout(8000);     // 8s
                conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14)");
                conn.setInstanceFollowRedirects(false);
                
                int code = conn.getResponseCode();
                return "OK:" + code;
            } catch (java.net.SocketTimeoutException e) {
                return "ERROR:连接超时(8秒)";
            } catch (java.net.ConnectException e) {
                return "ERROR:无法连接: " + e.getMessage();
            } catch (Exception e) {
                return "ERROR:" + e.getClass().getSimpleName() + ": " + e.getMessage();
            } finally {
                if (conn != null) try { conn.disconnect(); } catch (Exception e) {}
            }
        }
        
        /**
         * Test API with a minimal POST request using OkHttp
         * Returns response or error (async version)
         */
        @JavascriptInterface
        public void testApiPostAsync(String urlStr, String authHeader) {
            new Thread(() -> {
                okhttp3.MediaType JSON = okhttp3.MediaType.get("application/json; charset=utf-8");
                String body = "{\"model\":\"deepseek-chat\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":5}";
                okhttp3.RequestBody requestBody = okhttp3.RequestBody.create(body, JSON);
                
                okhttp3.Request.Builder requestBuilder = new okhttp3.Request.Builder()
                    .url(urlStr)
                    .post(requestBody)
                    .header("Accept", "application/json");
                
                if (authHeader != null && !authHeader.isEmpty()) {
                    requestBuilder.header("Authorization", authHeader);
                }
                
                try (okhttp3.Response response = httpClient.newCall(requestBuilder.build()).execute()) {
                    int code = response.code();
                    String responseBody = response.body() != null ? response.body().string() : "";
                    lastTestResult = "OK:" + code + ":" + responseBody.substring(0, Math.min(200, responseBody.length()));
                } catch (java.net.SocketTimeoutException e) {
                    lastTestResult = "ERROR:超时(15秒)";
                } catch (Exception e) {
                    lastTestResult = "ERROR:" + e.getClass().getSimpleName() + ":" + e.getMessage();
                }
                testComplete = true;
            }).start();
        }
        
        private volatile String lastTestResult = null;
        private volatile boolean testComplete = false;
        
        @JavascriptInterface
        public boolean isTestComplete() { return testComplete; }
        
        @JavascriptInterface
        public String getTestResult() { return lastTestResult; }
        
        @JavascriptInterface
        public void resetTest() { testComplete = false; lastTestResult = null; }
        
        /**
         * Start async HTTP POST request using OkHttp (reliable timeout)
         * JavaScript should poll isRequestComplete() and then get results
         */
        @JavascriptInterface
        public void startAsyncHttp(String urlStr, String jsonBody, String authHeader) {
            requestComplete = false;
            lastResponse = null;
            lastError = null;
            lastStatusCode = 0;
            
            Log.d(TAG, "startAsyncHttp: url=" + urlStr);
            
            new Thread(() -> {
                okhttp3.MediaType JSON = okhttp3.MediaType.get("application/json; charset=utf-8");
                okhttp3.RequestBody body = okhttp3.RequestBody.create(jsonBody, JSON);
                
                okhttp3.Request.Builder requestBuilder = new okhttp3.Request.Builder()
                    .url(urlStr)
                    .post(body)
                    .header("Accept", "application/json");
                
                if (authHeader != null && !authHeader.isEmpty()) {
                    requestBuilder.header("Authorization", authHeader);
                }
                
                try (okhttp3.Response response = httpClient.newCall(requestBuilder.build()).execute()) {
                    
                    lastStatusCode = response.code();
                    lastResponse = response.body() != null ? response.body().string() : "";
                    lastError = null;
                    Log.d(TAG, "OkHttp success: " + lastStatusCode + ", " + lastResponse.length() + " chars");
                    
                } catch (java.net.SocketTimeoutException e) {
                    Log.e(TAG, "OkHttp timeout: " + e.getMessage());
                    lastError = "请求超时(5分钟)";
                    lastStatusCode = -1;
                } catch (java.net.ConnectException e) {
                    Log.e(TAG, "OkHttp connect failed: " + e.getMessage());
                    lastError = "无法连接: " + e.getMessage();
                    lastStatusCode = -1;
                } catch (Exception e) {
                    Log.e(TAG, "OkHttp error: " + e.getClass().getSimpleName() + ": " + e.getMessage());
                    lastError = e.getMessage() != null ? e.getMessage() : "未知错误";
                    lastStatusCode = -1;
                }
                
                requestComplete = true;
                Log.d(TAG, "HTTP done: status=" + lastStatusCode);
            }).start();
        }
        
        @JavascriptInterface
        public boolean isRequestComplete() {
            return requestComplete;
        }
        
        @JavascriptInterface
        public int getLastStatusCode() {
            return lastStatusCode;
        }
        
        @JavascriptInterface
        public String getLastResponse() {
            return lastResponse;
        }
        
        @JavascriptInterface
        public String getLastError() {
            return lastError;
        }
    }
}

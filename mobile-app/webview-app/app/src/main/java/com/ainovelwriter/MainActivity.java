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

            // Initialize novels directory
            novelsDir = new File(getExternalFilesDir(null), "AI_NovelWriter");
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
            settings.setAllowFileAccessFromFileURLs(true);
            settings.setAllowUniversalAccessFromFileURLs(true);
            settings.setDatabaseEnabled(true);
            settings.setCacheMode(WebSettings.LOAD_DEFAULT);
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
            settings.setMediaPlaybackRequiresUserGesture(false);
            settings.setLoadWithOverviewMode(true);
            settings.setUseWideViewPort(true);
            settings.setBuiltInZoomControls(false);
            settings.setSupportZoom(false);
            settings.setBlockNetworkImage(false);
            settings.setBlockNetworkLoads(false);
            webView.setBackgroundColor(0xFF1a1a2e);

            // Disable debugging in production
            WebView.setWebContentsDebuggingEnabled(false);

            // Add JavascriptInterface
            webView.addJavascriptInterface(new NovelFileInterface(), "NovelFS");

            // Set WebView client
            webView.setWebViewClient(new WebViewClient() {
                @Override
                public boolean shouldOverrideUrlLoading(WebView view, String url) {
                    return false;
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
            // Move to background instead of closing
            moveTaskToBack(true);
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
                    while ((line = reader.readLine()) != null) {
                        sb.append(line).append("\n");
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
            File file = new File(novelsDir, novelName + "/" + relativePath);
            return file.exists();
        }
        
        @JavascriptInterface
        public String[] listFiles(String novelName, String relativePath) {
            try {
                File dir = new File(novelsDir, novelName + "/" + relativePath);
                if (!dir.exists() || !dir.isDirectory()) {
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
                File file = new File(novelsDir, novelName + "/" + relativePath);
                return file.exists() && file.delete();
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
                File novelDir = new File(novelsDir, novelName);
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
                    wakeLock.acquire(24 * 60 * 60 * 1000L); // 24 hours
                    Log.d(TAG, "Wake lock acquired (24h)");
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
         * Test network connectivity
         * Returns: "OK" or error message
         */
        @JavascriptInterface
        public String testConnection(String urlStr) {
            try {
                URL url = new URL(urlStr);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);
                conn.setRequestProperty("User-Agent", "AINovelWriter/2.13.1 Android");
                
                int code = conn.getResponseCode();
                conn.disconnect();
                return "OK:" + code;
            } catch (Exception e) {
                Log.e(TAG, "Test connection failed: " + e.getMessage());
                return "ERROR:" + e.getMessage();
            }
        }
        
        /**
         * Start async HTTP POST request in background thread
         * JavaScript should poll isRequestComplete() and then get results
         */
        @JavascriptInterface
        public void startAsyncHttp(String urlStr, String jsonBody, String authHeader) {
            requestComplete = false;
            lastResponse = null;
            lastError = null;
            lastStatusCode = 0;
            
            Log.d(TAG, "startAsyncHttp: url=" + urlStr + ", authLen=" + (authHeader != null ? authHeader.length() : 0));
            
            new Thread(() -> {
                int maxRetries = 3;
                
                for (int attempt = 1; attempt <= maxRetries; attempt++) {
                    HttpURLConnection conn = null;
                    try {
                        URL url = new URL(urlStr);
                        conn = (HttpURLConnection) url.openConnection();
                        
                        // For HTTPS, configure SSL
                        if (conn instanceof javax.net.ssl.HttpsURLConnection) {
                            javax.net.ssl.HttpsURLConnection httpsConn = (javax.net.ssl.HttpsURLConnection) conn;
                            // Use default SSL (don't trust all certs in production)
                            // Only override if needed
                            try {
                                // Try to use the system's default SSL context first
                                javax.net.ssl.SSLContext sslContext = javax.net.ssl.SSLContext.getInstance("TLSv1.2");
                                sslContext.init(null, null, new java.security.SecureRandom());
                                httpsConn.setSSLSocketFactory(sslContext.getSocketFactory());
                            } catch (Exception sslE) {
                                Log.w(TAG, "SSL config failed, using defaults: " + sslE.getMessage());
                            }
                        }
                        
                        conn.setRequestMethod("POST");
                        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                        conn.setRequestProperty("Accept", "application/json");
                        conn.setRequestProperty("User-Agent", "AINovelWriter/2.13.1 Android");
                        conn.setRequestProperty("Connection", "close");
                        conn.setRequestProperty("Accept-Encoding", "identity");
                        
                        if (authHeader != null && !authHeader.isEmpty()) {
                            conn.setRequestProperty("Authorization", authHeader);
                        }
                        
                        conn.setDoOutput(true);
                        conn.setDoInput(true);
                        conn.setConnectTimeout(30000);  // 30s connect
                        conn.setReadTimeout(120000);     // 2min read
                        conn.setInstanceFollowRedirects(true);
                        
                        Log.d(TAG, "HTTP attempt " + attempt + ": connecting to " + urlStr + "...");
                        
                        // Write request body
                        try (OutputStream os = conn.getOutputStream()) {
                            os.write(jsonBody.getBytes("UTF-8"));
                            os.flush();
                        }
                        
                        int responseCode = conn.getResponseCode();
                        Log.d(TAG, "HTTP Response: " + responseCode + " (attempt " + attempt + ")");
                        
                        // Read response
                        StringBuilder response = new StringBuilder();
                        try (BufferedReader br = new BufferedReader(
                                new InputStreamReader(
                                    responseCode >= 200 && responseCode < 300 
                                        ? conn.getInputStream() 
                                        : conn.getErrorStream(), 
                                    "UTF-8"))) {
                            String line;
                            while ((line = br.readLine()) != null) {
                                response.append(line);
                            }
                        }
                        
                        lastResponse = response.toString();
                        lastError = null;
                        lastStatusCode = responseCode;
                        Log.d(TAG, "HTTP success: " + lastResponse.length() + " chars");
                        break; // Success
                        
                    } catch (java.net.SocketTimeoutException e) {
                        Log.e(TAG, "Timeout (attempt " + attempt + "): " + e.getMessage());
                        lastException = e;
                        if (attempt == maxRetries) {
                            lastError = "连接超时，请检查网络或API端点";
                            lastStatusCode = -1;
                        } else {
                            try { Thread.sleep(2000); } catch (InterruptedException ie) { break; }
                        }
                    } catch (java.net.ConnectException e) {
                        Log.e(TAG, "Connect failed (attempt " + attempt + "): " + e.getMessage());
                        lastException = e;
                        lastError = "无法连接到服务器: " + e.getMessage();
                        lastStatusCode = -1;
                        break; // Don't retry on connect failure
                    } catch (java.net.SocketException e) {
                        Log.e(TAG, "Socket error (attempt " + attempt + "): " + e.getMessage());
                        lastException = e;
                        if (attempt == maxRetries) {
                            lastError = "网络连接被中断: " + e.getMessage();
                            lastStatusCode = -1;
                        } else {
                            try { Thread.sleep(3000); } catch (InterruptedException ie) { break; }
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "HTTP error (attempt " + attempt + "): " + e.getClass().getSimpleName() + ": " + e.getMessage());
                        lastException = e;
                        if (attempt == maxRetries) {
                            lastError = e.getMessage();
                            lastStatusCode = -1;
                        } else {
                            try { Thread.sleep(2000); } catch (InterruptedException ie) { break; }
                        }
                    } finally {
                        if (conn != null) {
                            conn.disconnect();
                        }
                    }
                }
                requestComplete = true;
                Log.d(TAG, "HTTP request done: status=" + lastStatusCode);
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

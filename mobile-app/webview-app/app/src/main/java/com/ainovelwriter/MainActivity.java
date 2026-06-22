package com.ainovelwriter;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
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
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.graphics.Bitmap;
import android.widget.Toast;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.BufferedReader;
import java.io.FileReader;

public class MainActivity extends Activity {
    private static final String TAG = "AINovelWriter";
    private WebView webView;
    private File novelsDir;
    private PowerManager.WakeLock wakeLock;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Fullscreen
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_FULLSCREEN,
            WindowManager.LayoutParams.FLAG_FULLSCREEN
        );

        // Keep screen on during generation
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // Initialize novels directory
        novelsDir = new File(getExternalFilesDir(null), "AI_NovelWriter");
        if (!novelsDir.exists()) {
            novelsDir.mkdirs();
        }

        // Initialize wake lock
        PowerManager powerManager = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AINovelWriter::Generation");
        
        // Start foreground service to keep alive
        startForegroundService();

        webView = new WebView(this);
        setContentView(webView);

        // Configure WebView
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowUniversalAccessFromFileURLs(true);
        settings.setDatabaseEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);
        settings.setSupportZoom(false);
        // Prevent white flash
        webView.setBackgroundColor(0xFF1a1a2e);

        // Enable debugging (remote inspector via chrome://inspect)
        WebView.setWebContentsDebuggingEnabled(true);

        // Add JavascriptInterface for file operations
        webView.addJavascriptInterface(new NovelFileInterface(), "NovelFS");

        // Set WebView client with comprehensive error logging
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Log.d(TAG, "shouldOverrideUrlLoading: " + url);
                if (url.startsWith("file:///android_asset/")) {
                    return false;
                }
                return false;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                Log.d(TAG, "Page started: " + url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                Log.d(TAG, "Page finished: " + url);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                Log.e(TAG, "Resource error: code=" + error.getErrorCode() + 
                      " desc=" + error.getDescription() + 
                      " url=" + (request != null ? request.getUrl() : "null"));
            }

            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                Log.e(TAG, "Page error: code=" + errorCode + 
                      " desc=" + description + " url=" + failingUrl);
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                Log.e(TAG, "HTTP error: " + errorResponse.getStatusCode() + 
                      " for " + request.getUrl());
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onConsoleMessage(ConsoleMessage consoleMessage) {
                String msg = consoleMessage.message();
                Log.d(TAG, "JS [" + consoleMessage.messageLevel() + "] " + 
                      (msg.length() > 200 ? msg.substring(0, 200) + "..." : msg));
                return true;
            }
        });

        Log.d(TAG, "Loading index.html from assets");
        Log.d(TAG, "Novels directory: " + novelsDir.getAbsolutePath());
        webView.loadUrl("file:///android_asset/index.html");
    }

    private void startForegroundService() {
        try {
            Intent serviceIntent = new Intent(this, KeepAliveService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(serviceIntent);
            } else {
                startService(serviceIntent);
            }
        } catch (Exception e) {
            Log.e(TAG, "Failed to start foreground service: " + e.getMessage());
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        // Release wake lock
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        
        // Stop foreground service
        try {
            stopService(new Intent(this, KeepAliveService.class));
        } catch (Exception e) {
            Log.e(TAG, "Failed to stop service: " + e.getMessage());
        }
        
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    /**
     * JavascriptInterface for novel file operations and keep-alive
     */
    public class NovelFileInterface {
        
        @JavascriptInterface
        public String getNovelsDir() {
            return novelsDir.getAbsolutePath();
        }
        
        @JavascriptInterface
        public boolean createNovelDir(String novelName) {
            try {
                File novelDir = new File(novelsDir, novelName);
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
                
                Log.d(TAG, "Created novel directory structure: " + novelDir.getAbsolutePath());
                return true;
            } catch (Exception e) {
                Log.e(TAG, "Failed to create novel dir: " + e.getMessage());
                return false;
            }
        }
        
        @JavascriptInterface
        public boolean writeFile(String novelName, String relativePath, String content) {
            try {
                File file = new File(novelsDir, novelName + "/" + relativePath);
                File parentDir = file.getParentFile();
                if (parentDir != null && !parentDir.exists()) {
                    parentDir.mkdirs();
                }
                FileWriter writer = new FileWriter(file);
                writer.write(content);
                writer.flush();
                writer.close();
                return true;
            } catch (IOException e) {
                Log.e(TAG, "Failed to write file: " + e.getMessage());
                return false;
            }
        }
        
        @JavascriptInterface
        public String readFile(String novelName, String relativePath) {
            try {
                File file = new File(novelsDir, novelName + "/" + relativePath);
                if (!file.exists()) {
                    return null;
                }
                BufferedReader reader = new BufferedReader(new FileReader(file));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line).append("\n");
                }
                reader.close();
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
                if (!novelsDir.exists()) {
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
                if (!wakeLock.isHeld()) {
                    wakeLock.acquire(60 * 60 * 1000L); // 1 hour max
                    Log.d(TAG, "Wake lock acquired");
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to acquire wake lock: " + e.getMessage());
            }
        }
        
        @JavascriptInterface
        public void releaseWakeLock() {
            try {
                if (wakeLock.isHeld()) {
                    wakeLock.release();
                    Log.d(TAG, "Wake lock released");
                }
            } catch (Exception e) {
                Log.e(TAG, "Failed to release wake lock: " + e.getMessage());
            }
        }
    }

    /**
     * Foreground service to keep app alive during generation
     */
    public static class KeepAliveService extends Service {
        private static final String CHANNEL_ID = "AINovelWriter_Service";
        private static final int NOTIFICATION_ID = 1001;

        @Override
        public void onCreate() {
            super.onCreate();
            createNotificationChannel();
            startForeground(NOTIFICATION_ID, createNotification());
        }

        @Override
        public int onStartCommand(Intent intent, int flags, int startId) {
            return START_STICKY;
        }

        @Override
        public IBinder onBind(Intent intent) {
            return null;
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
                .setContentText("正在创作中...")
                .setSmallIcon(android.R.drawable.ic_menu_edit)
                .setContentIntent(pendingIntent)
                .setOngoing(true)
                .build();
        }

        @Override
        public void onDestroy() {
            super.onDestroy();
        }
    }
}

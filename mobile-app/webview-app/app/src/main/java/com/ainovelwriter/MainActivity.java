package com.ainovelwriter;

import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebChromeClient;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;

public class MainActivity extends Activity {
    private static final String TAG = "AINovelWriter";
    private WebView webView;
    private File novelsDir;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Log.d(TAG, "=== onCreate START ===");

        try {
            // 初始化小说目录
            File externalDir = getExternalFilesDir(null);
            if (externalDir == null) externalDir = getFilesDir();
            novelsDir = new File(externalDir, "AI_NovelWriter");
            if (!novelsDir.exists()) novelsDir.mkdirs();
            Log.d(TAG, "novelsDir: " + novelsDir.getAbsolutePath());

            // 创建WebView
            webView = new WebView(this);
            setContentView(webView);
            Log.d(TAG, "WebView created, setContentView done");

            // 配置
            WebSettings s = webView.getSettings();
            s.setJavaScriptEnabled(true);
            s.setDomStorageEnabled(true);
            s.setAllowFileAccess(true);
            s.setAllowContentAccess(true);

            // 调试
            WebView.setWebContentsDebuggingEnabled(true);

            // JS接口
            webView.addJavascriptInterface(new NovelFileInterface(), "NovelFS");

            // WebViewClient
            webView.setWebViewClient(new WebViewClient());
            webView.setWebChromeClient(new WebChromeClient());

            // 加载HTML
            String html = readAssetFile("index.html");
            Log.d(TAG, "HTML length: " + (html != null ? html.length() : "null"));

            if (html != null && !html.isEmpty()) {
                webView.loadDataWithBaseURL("file:///android_asset/", html, "text/html", "UTF-8", null);
                Log.d(TAG, "loadDataWithBaseURL called");
            } else {
                Log.e(TAG, "HTML is null/empty!");
                webView.loadData("<h1>ERROR: index.html not found</h1>", "text/html", "UTF-8");
            }

        } catch (Exception e) {
            Log.e(TAG, "FATAL: " + e.getMessage(), e);
        }
        Log.d(TAG, "=== onCreate END ===");
    }

    private String readAssetFile(String fileName) {
        try {
            java.io.InputStream is = getAssets().open(fileName);
            BufferedReader r = new BufferedReader(new InputStreamReader(is, "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line).append("\n");
            r.close();
            is.close();
            return sb.toString();
        } catch (Exception e) {
            Log.e(TAG, "readAssetFile fail: " + e.getMessage());
            return null;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else moveTaskToBack(true);
    }

    @Override protected void onPause() { super.onPause(); if (webView != null) { webView.onPause(); webView.pauseTimers(); } }
    @Override protected void onResume() { super.onResume(); if (webView != null) { webView.onResume(); webView.resumeTimers(); } }
    @Override protected void onDestroy() { if (webView != null) webView.destroy(); super.onDestroy(); }

    // ==================== NovelFS JavaScript Interface ====================
    public class NovelFileInterface {
        private volatile String lastResponse, lastError;
        private volatile int lastStatusCode;
        private volatile boolean requestComplete;

        private File getSafeFile(String novel, String path) {
            try {
                String n = novel.replaceAll("[\\\\/]","_").replaceAll("\\.\\.","");
                String p = path.replaceAll("\\\\","/").replaceAll("\\.\\.","");
                File f = new File(novelsDir, n + "/" + p);
                if (!f.getCanonicalPath().startsWith(novelsDir.getCanonicalPath())) return null;
                return f;
            } catch (Exception e) { return null; }
        }

        @JavascriptInterface public String getNovelsDir() { return novelsDir != null ? novelsDir.getAbsolutePath() : ""; }

        @JavascriptInterface public boolean createNovelDir(String name) {
            try {
                File d = getSafeFile(name, "");
                if (d == null) return false;
                if (!d.exists()) d.mkdirs();
                for (String sub : new String[]{"chapters","characters","outlines","memory","backups","summaries","notes"})
                    new File(d, sub).mkdirs();
                return true;
            } catch (Exception e) { return false; }
        }

        @JavascriptInterface public boolean writeFile(String novel, String file, String content) {
            try {
                File f = getSafeFile(novel, file);
                if (f == null) return false;
                f.getParentFile().mkdirs();
                java.io.FileWriter w = new java.io.FileWriter(f, false);
                w.write(content);
                w.close();
                return true;
            } catch (Exception e) { return false; }
        }

        @JavascriptInterface public String readFile(String novel, String file) {
            try {
                File f = getSafeFile(novel, file);
                if (f == null || !f.exists()) return null;
                BufferedReader r = new BufferedReader(new java.io.FileReader(f));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = r.readLine()) != null) sb.append(line).append("\n");
                r.close();
                return sb.toString();
            } catch (Exception e) { return null; }
        }

        @JavascriptInterface public String[] listNovels() {
            try {
                if (novelsDir == null || !novelsDir.exists()) return new String[0];
                File[] dirs = novelsDir.listFiles(File::isDirectory);
                if (dirs == null) return new String[0];
                String[] names = new String[dirs.length];
                for (int i = 0; i < dirs.length; i++) names[i] = dirs[i].getName();
                return names;
            } catch (Exception e) { return new String[0]; }
        }

        @JavascriptInterface public boolean deleteNovel(String name) {
            try {
                File d = getSafeFile(name, "");
                if (d == null || !d.exists()) return false;
                del(d);
                return true;
            } catch (Exception e) { return false; }
        }
        private void del(File f) { if (f.isDirectory()) { File[] c = f.listFiles(); if (c != null) for (File x : c) del(x); } f.delete(); }

        @JavascriptInterface public void startAsyncHttp(String url, String body, String auth) {
            requestComplete = false; lastResponse = null; lastError = null; lastStatusCode = 0;
            new Thread(() -> {
                try {
                    java.net.HttpURLConnection c = (java.net.HttpURLConnection) new java.net.URL(url).openConnection();
                    c.setRequestMethod("POST");
                    c.setRequestProperty("Content-Type", "application/json");
                    c.setRequestProperty("Accept", "application/json");
                    if (auth != null && !auth.isEmpty()) {
                        if (auth.startsWith("x-api-key:")) { c.setRequestProperty("x-api-key", auth.substring(10)); c.setRequestProperty("anthropic-version", "2023-06-01"); }
                        else c.setRequestProperty("Authorization", auth);
                    }
                    c.setDoOutput(true);
                    c.setConnectTimeout(15000);
                    c.setReadTimeout(300000);
                    c.getOutputStream().write(body.getBytes("UTF-8"));
                    c.getOutputStream().flush();
                    c.getOutputStream().close();
                    lastStatusCode = c.getResponseCode();
                    java.io.InputStream is = lastStatusCode >= 400 ? c.getErrorStream() : c.getInputStream();
                    BufferedReader r = new BufferedReader(new InputStreamReader(is, "UTF-8"));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = r.readLine()) != null) sb.append(line).append("\n");
                    r.close();
                    lastResponse = sb.toString();
                } catch (Exception e) { lastError = e.getMessage(); lastStatusCode = -1; }
                requestComplete = true;
            }).start();
        }

        @JavascriptInterface public boolean isRequestComplete() { return requestComplete; }
        @JavascriptInterface public String getLastResponse() { return lastResponse; }
        @JavascriptInterface public String getLastError() { return lastError; }
        @JavascriptInterface public int getLastStatusCode() { return lastStatusCode; }
    }
}

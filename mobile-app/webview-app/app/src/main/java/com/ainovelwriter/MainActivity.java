package com.ainovelwriter;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.graphics.Bitmap;

public class MainActivity extends Activity {
    private static final String TAG = "AINovelWriter";
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Fullscreen
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_FULLSCREEN,
            WindowManager.LayoutParams.FLAG_FULLSCREEN
        );

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

        // Set WebView client with comprehensive error logging
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Log.d(TAG, "shouldOverrideUrlLoading: " + url);
                // Only load URLs within our app
                if (url.startsWith("file:///android_asset/")) {
                    return false; // Let WebView handle it
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
                // Inject error checker
                view.evaluateJavascript(
                    "(function(){ " +
                    "  var root = document.getElementById('root'); " +
                    "  var err = document.getElementById('app-error'); " +
                    "  var load = document.getElementById('app-loading'); " +
                    "  return JSON.stringify({ " +
                    "    rootChildren: root ? root.children.length : -1, " +
                    "    errorVisible: err ? err.style.display : 'none', " +
                    "    loadingVisible: load ? load.style.display : 'none' " +
                    "  }); " +
                    "})()",
                    value -> Log.d(TAG, "Page state: " + value)
                );
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
                // Log all JS console messages with level
                Log.d(TAG, "JS [" + consoleMessage.messageLevel() + "] " + 
                      (msg.length() > 200 ? msg.substring(0, 200) + "..." : msg));
                return true;
            }
        });

        // Load the Expo app
        Log.d(TAG, "Loading index.html from assets");
        webView.loadUrl("file:///android_asset/index.html");
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
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}

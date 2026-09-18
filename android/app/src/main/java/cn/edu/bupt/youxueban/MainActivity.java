package cn.edu.bupt.youxueban;

import android.Manifest;
import android.app.*;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.security.keystore.*;
import android.util.AtomicFile;
import android.util.Base64;
import android.util.Log;
import android.view.*;
import android.webkit.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;

public final class MainActivity extends Activity {
    private static final String HOST = "appassets.androidplatform.net";
    private static final String BASE = "https://" + HOST;
    private static final String TAG = "YouXueBan";
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService workers = Executors.newFixedThreadPool(6);
    private final Map<Integer, CampusWindow> windows = new ConcurrentHashMap<>();
    private final Map<String, HttpURLConnection> connections = new ConcurrentHashMap<>();
    private final AtomicInteger nextWindow = new AtomicInteger();
    private final Set<String> origins = new HashSet<>();
    private FrameLayout root;
    private WebView ui, runtime;
    private LinearLayout campusOverlay;
    private TextView startup;
    private ValueCallback<Uri[]> fileCallback;
    private volatile boolean ready, closed;

    private static final class CampusWindow {
        WebView view;
        volatile String url = "about:blank";
        String navigation;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        WebView.setWebContentsDebuggingEnabled((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0);
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.WHITE);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            } else view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(root);
        startup = new TextView(this);
        startup.setText("邮学伴正在启动…");
        startup.setTextSize(18);
        startup.setGravity(Gravity.CENTER);
        root.addView(startup, new FrameLayout.LayoutParams(-1, -1));
        try {
            runtime = localWebView("runtime");
            runtime.addJavascriptInterface(new RuntimeBridge(), "NativeRuntime");
            root.addView(runtime, 0, new FrameLayout.LayoutParams(1, 1));
            runtime.loadUrl(BASE + "/runtime/index.html");
        } catch (Exception error) { startupError("无法初始化 Android WebView，请更新系统 WebView 后重试。"); }
        main.postDelayed(() -> {
            if (!ready) startupError("设备内运行时未能启动，请重新打开应用或更新 Android System WebView。");
        }, 20_000);
        getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel("reminders", "课程与任务提醒", NotificationManager.IMPORTANCE_DEFAULT));
    }

    private WebView configuredWebView() {
        WebView view = new WebView(this);
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setMediaPlaybackRequiresUserGesture(true);
        view.setBackgroundColor(Color.WHITE);
        return view;
    }

    private WebView localWebView(String directory) {
        WebView view = configuredWebView();
        view.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView web, WebResourceRequest request) {
                Uri url = request.getUrl();
                if (!HOST.equals(url.getHost()) || !"https".equals(url.getScheme())) {
                    return "runtime".equals(directory) ? missing() : super.shouldInterceptRequest(web, request);
                }
                String path = url.getPath();
                if (path == null || !path.startsWith("/" + directory + "/") || path.contains("..") || path.contains("\\")) return missing();
                try {
                    String mime = "application/octet-stream";
                    if (path.endsWith(".html")) mime = "text/html";
                    else if (path.endsWith(".js")) mime = "application/javascript";
                    else if (path.endsWith(".css")) mime = "text/css";
                    else if (path.endsWith(".svg")) mime = "image/svg+xml";
                    else if (path.endsWith(".png")) mime = "image/png";
                    else if (path.endsWith(".woff2")) mime = "font/woff2";
                    WebResourceResponse response = new WebResourceResponse(mime, "UTF-8", getAssets().open(path.substring(1)));
                    response.setResponseHeaders(Map.of(
                        "X-Content-Type-Options", "nosniff", "Cache-Control", "no-cache",
                        "Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http://*.bupt.edu.cn; font-src 'self' data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'"));
                    return response;
                } catch (Exception error) { return missing(); }
            }
            @Override public boolean shouldOverrideUrlLoading(WebView web, WebResourceRequest request) {
                if (request.isForMainFrame()) {
                    if ("web".equals(directory)) openExternal(request.getUrl());
                    return true;
                }
                return !HOST.equals(request.getUrl().getHost());
            }
            @Override public void onReceivedError(WebView web, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) startupError("本地页面加载失败，请重新安装完整 APK。");
            }
            @Override public boolean onRenderProcessGone(WebView web, RenderProcessGoneDetail detail) {
                ready = false;
                startupError("系统已终止网页运行进程，请关闭并重新打开邮学伴。");
                return true;
            }
            @Override public void onPageFinished(WebView web, String url) {
                if ("web".equals(directory)) main.postDelayed(() -> {
                    if (!closed) web.evaluateJavascript("Boolean(document.querySelector('#app')?.children.length)",
                        result -> { if ("false".equals(result)) startupError("界面未能初始化，请重新安装或更新系统 WebView。"); });
                }, 8000);
            }
        });
        view.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onConsoleMessage(ConsoleMessage message) {
                // Never log console contents: they can contain personal/upstream data.
                if (message.messageLevel() == ConsoleMessage.MessageLevel.ERROR)
                    Log.e(TAG, "WebView script error at line " + message.lineNumber() + " (" + directory + ")");
                return true;
            }
            @Override public boolean onShowFileChooser(WebView web, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (!"web".equals(directory)) return false;
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    Intent intent = params.createIntent();
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(intent, 40);
                } catch (Exception error) { fileCallback.onReceiveValue(null); fileCallback = null; }
                return true;
            }
            @Override public boolean onCreateWindow(WebView web, boolean dialog, boolean gesture, Message result) {
                WebView popup = new WebView(MainActivity.this);
                popup.setWebViewClient(new WebViewClient() {
                    @Override public boolean shouldOverrideUrlLoading(WebView child, WebResourceRequest request) {
                        openExternal(request.getUrl());
                        child.destroy();
                        return true;
                    }
                });
                ((WebView.WebViewTransport) result.obj).setWebView(popup);
                result.sendToTarget();
                return true;
            }
        });
        if ("web".equals(directory)) view.getSettings().setSupportMultipleWindows(true);
        return view;
    }

    private static WebResourceResponse missing() {
        return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found", Map.of(),
            new ByteArrayInputStream("Not found".getBytes(StandardCharsets.UTF_8)));
    }
    private void startupError(String message) {
        main.post(() -> {
            if (closed) return;
            if (startup.getParent() == null) root.addView(startup, new FrameLayout.LayoutParams(-1, -1));
            startup.setBackgroundColor(Color.WHITE);
            startup.setText("邮学伴启动失败\n\n" + message);
            startup.bringToFront();
            Log.e(TAG, "Application startup failed");
        });
    }
    private void openExternal(Uri uri) {
        if (!"https".equals(uri.getScheme()) && !"http".equals(uri.getScheme())) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
        catch (Exception error) { Toast.makeText(this, "没有可用的浏览器", Toast.LENGTH_SHORT).show(); }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == 40 && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
            fileCallback = null;
        }
    }
    private void eval(WebView view, String script) {
        main.post(() -> { if (!closed && view != null) view.evaluateJavascript(script, null); });
    }
    private void nativeResult(String id, Object value, String error) {
        String encoded = value instanceof String ? JSONObject.quote((String) value) :
            value == null ? "null" : JSONObject.wrap(value).toString();
        eval(runtime, "window.__nativeResult(" + JSONObject.quote(id) + "," + encoded + "," +
            (error == null ? "null" : JSONObject.quote(error)) + ")");
    }
    private void replyUi(String id, String json) {
        try { eval(ui, "window.__androidReply(" + JSONObject.quote(id) + "," + new JSONObject(json) + ")"); }
        catch (Exception ignored) { }
    }
    public final class UiBridge {
        @JavascriptInterface public void cancel(String id) {
            if (id.length() <= 32) eval(runtime, "window.__cancelRequest(" + JSONObject.quote(id) + ")");
        }
        @JavascriptInterface public void request(String id, String route, String init) {
            if (id.length() > 32 || route.length() > 200 || init.length() > 24_000_000) return;
            if (!ready || !route.startsWith("/api/")) {
                replyUi(id, "{\"status\":503,\"body\":{\"error\":\"设备运行时尚未就绪\"}}");
                return;
            }
            try { eval(runtime, "window.__request(" + JSONObject.quote(id) + "," + JSONObject.quote(route) + "," + new JSONObject(init) + ")"); }
            catch (Exception error) { replyUi(id, "{\"status\":400,\"body\":{\"error\":\"请求格式无效\"}}"); }
        }
        @JavascriptInterface public boolean notify(String title, String body) {
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                main.post(() -> requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 41));
                return false;
            }
            PendingIntent intent = PendingIntent.getActivity(MainActivity.this, 0,
                new Intent(MainActivity.this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            Notification notification = new Notification.Builder(MainActivity.this, "reminders")
                .setSmallIcon(android.R.drawable.ic_popup_reminder).setContentTitle(limit(title, 80))
                .setContentText(limit(body, 500)).setStyle(new Notification.BigTextStyle().bigText(limit(body, 500)))
                .setContentIntent(intent).setAutoCancel(true).build();
            getSystemService(NotificationManager.class).notify((int) System.currentTimeMillis(), notification);
            return true;
        }
    }

    public final class RuntimeBridge {
        @JavascriptInterface public void ready() {
            main.post(() -> {
                if (ready || closed) return;
                ready = true;
                ui = localWebView("web");
                ui.addJavascriptInterface(new UiBridge(), "AndroidUI");
                root.addView(ui, new FrameLayout.LayoutParams(-1, -1));
                root.removeView(startup);
                ui.loadUrl(BASE + "/web/index.html");
                Log.i(TAG, "Native runtime ready");
            });
        }
        @JavascriptInterface public void reply(String id, String json) { replyUi(id, json); }
        @JavascriptInterface public String file(String operation, String name, String value) {
            synchronized (MainActivity.this) {
                try {
                    String leaf = name.substring(name.lastIndexOf('/') + 1);
                    if (!leaf.equals("local-settings.bin") && !leaf.equals("campus-cache.json")) throw new Exception();
                    AtomicFile file = new AtomicFile(new File(getFilesDir(), leaf));
                    Object result;
                    switch (operation) {
                        case "exists": result = file.getBaseFile().exists(); break;
                        case "read":
                            byte[] saved = file.readFully();
                            Cipher decrypt = Cipher.getInstance("AES/GCM/NoPadding");
                            decrypt.init(Cipher.DECRYPT_MODE, encryptionKey(),
                                new GCMParameterSpec(128, Arrays.copyOfRange(saved, 0, 12)));
                            result = new String(decrypt.doFinal(saved, 12, saved.length - 12), StandardCharsets.UTF_8);
                            break;
                        case "write":
                            Cipher encrypt = Cipher.getInstance("AES/GCM/NoPadding");
                            encrypt.init(Cipher.ENCRYPT_MODE, encryptionKey());
                            FileOutputStream output = null;
                            try {
                                output = file.startWrite();
                                output.write(encrypt.getIV());
                                output.write(encrypt.doFinal(value.getBytes(StandardCharsets.UTF_8)));
                                file.finishWrite(output);
                            } catch (Exception error) { file.failWrite(output); throw error; }
                            result = true;
                            break;
                        default: throw new Exception();
                    }
                    return new JSONObject().put("value", result).toString();
                } catch (Exception error) { return "{\"error\":\"设备加密存储读写失败\"}"; }
            }
        }
        @JavascriptInterface public String sha256(String value) {
            try {
                byte[] hash = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
                StringBuilder text = new StringBuilder();
                for (byte b : hash) text.append(String.format("%02x", b & 255));
                return text.toString();
            } catch (Exception error) { throw new IllegalStateException("SHA-256 unavailable"); }
        }
        @JavascriptInterface public int createWindow() {
            int id = nextWindow.incrementAndGet();
            CampusWindow window = new CampusWindow();
            windows.put(id, window);
            main.post(() -> createCampusWindow(id, window));
            return id;
        }
        @JavascriptInterface public String windowUrl(int id) {
            CampusWindow window = windows.get(id);
            return window == null ? "about:blank" : window.url;
        }
        @JavascriptInterface public void call(String id, String operation, String payload) {
            try {
                JSONObject args = new JSONObject(payload);
                if (operation.equals("cancelFetch")) {
                    HttpURLConnection connection = connections.remove(args.optString("id"));
                    if (connection != null) workers.execute(connection::disconnect);
                } else if (operation.equals("fetch")) workers.execute(() -> {
                    try { nativeResult(id, network(id, args), null); }
                    catch (Exception error) { nativeResult(id, null, "网络请求失败，请检查网络、校园网连接或稍后重试"); }
                });
                else main.post(() -> campusCall(id, operation, args));
            } catch (Exception error) { nativeResult(id, null, "设备请求格式无效"); }
        }
    }

    private SecretKey encryptionKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        String alias = "youxueban-local-v1";
        if (!store.containsAlias(alias)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(alias, null);
    }
    private static String limit(String value, int maximum) {
        return value == null ? "" : value.substring(0, Math.min(value.length(), maximum));
    }
    private static boolean campusUrl(String address) {
        try {
            URL url = new URL(address);
            String host = url.getHost().toLowerCase(Locale.ROOT);
            return (url.getProtocol().equals("https") || url.getProtocol().equals("http")) &&
                (host.equals("bupt.edu.cn") || host.endsWith(".bupt.edu.cn")) &&
                url.getUserInfo() == null && (url.getPort() == -1 || url.getPort() == 443 || url.getPort() == 80);
        } catch (Exception error) { return false; }
    }
    private void createCampusWindow(int id, CampusWindow window) {
        if (closed || !windows.containsKey(id)) return;
        WebView view = configuredWebView();
        window.view = view;
        android.webkit.CookieManager.getInstance().setAcceptThirdPartyCookies(view, true);
        view.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        // Untrusted campus pages have no JavaScript interface.
        view.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView web, WebResourceRequest request) {
                return !campusUrl(request.getUrl().toString());
            }
            @Override public void onPageStarted(WebView web, String url, android.graphics.Bitmap icon) {
                window.url = url;
                if (campusUrl(url)) origins.add(Uri.parse(url).getScheme() + "://" + Uri.parse(url).getHost());
            }
            @Override public void onPageFinished(WebView web, String url) {
                window.url = url;
                android.webkit.CookieManager.getInstance().flush();
                if (window.navigation != null) {
                    nativeResult(window.navigation, true, null);
                    window.navigation = null;
                }
            }
            @Override public void onReceivedError(WebView web, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame() && window.navigation != null) {
                    nativeResult(window.navigation, null, "校园登录页面加载失败，请检查校园网连接");
                    window.navigation = null;
                }
            }
        });
        view.setWebChromeClient(new WebChromeClient());
        root.addView(view, 0, new FrameLayout.LayoutParams(-1, -1));
    }
    private void campusCall(String id, String operation, JSONObject args) {
        try {
            android.webkit.CookieManager cookies = android.webkit.CookieManager.getInstance();
            if (operation.equals("clearSessions")) {
                for (String origin : origins) WebStorage.getInstance().deleteOrigin(origin);
                for (String host : List.of("auth.bupt.edu.cn", "jwgl.bupt.edu.cn", "dekt.bupt.edu.cn", "my.bupt.edu.cn", "app.bupt.edu.cn")) {
                    WebStorage.getInstance().deleteOrigin("https://" + host);
                    WebStorage.getInstance().deleteOrigin("http://" + host);
                }
                cookies.removeAllCookies(done -> { cookies.flush(); nativeResult(id, true, null); });
                return;
            }
            if (operation.equals("cookies")) {
                JSONArray result = new JSONArray();
                for (String host : List.of("auth.bupt.edu.cn", "my.bupt.edu.cn", "app.bupt.edu.cn", "jwgl.bupt.edu.cn", "dekt.bupt.edu.cn")) {
                    String address = (host.equals("my.bupt.edu.cn") ? "http://" : "https://") + host +
                        (host.equals("app.bupt.edu.cn") ? "/buptdf/wap/default/chong" : "/");
                    String value = cookies.getCookie(address);
                    if (value == null) continue;
                    for (String part : value.split(";")) {
                        int equal = part.indexOf('=');
                        if (equal < 1) continue;
                        result.put(new JSONObject().put("name", part.substring(0, equal).trim())
                            .put("value", part.substring(equal + 1).trim()).put("domain", host).put("path", "/")
                            .put("expires", -1).put("secure", !host.equals("my.bupt.edu.cn")).put("httpOnly", true));
                    }
                }
                nativeResult(id, result, null);
                return;
            }
            if (operation.equals("setCookies")) {
                JSONArray values = args.optJSONArray("cookies");
                if (values != null) for (int index = 0; index < values.length(); index++) {
                    JSONObject cookie = values.getJSONObject(index);
                    String host = cookie.optString("domain").replaceFirst("^\\.", "");
                    String address = "https://" + host;
                    if (!campusUrl(address)) continue;
                    String name = cookie.optString("name"), value = cookie.optString("value");
                    if (name.matches("[A-Za-z0-9_.-]+") && !value.contains(";") && !value.contains("\r") && !value.contains("\n"))
                        cookies.setCookie(address, name + "=" + value + "; Path=/; HttpOnly" + (cookie.optBoolean("secure") ? "; Secure" : ""));
                }
                cookies.flush();
                nativeResult(id, true, null);
                return;
            }
            int windowId = args.getInt("window");
            CampusWindow window = windows.get(windowId);
            if (window == null || window.view == null) throw new Exception();
            switch (operation) {
                case "navigate":
                    String address = args.getString("url");
                    if (!campusUrl(address)) throw new Exception();
                    window.navigation = id;
                    window.view.loadUrl(address);
                    main.postDelayed(() -> {
                        if (id.equals(window.navigation)) {
                            window.navigation = null;
                            nativeResult(id, null, "校园登录页面加载超时，请重试");
                        }
                    }, 35_000);
                    return;
                case "evaluate":
                    if (!campusUrl(window.url)) throw new Exception();
                    window.view.evaluateJavascript(args.getString("script"), result -> {
                        try { nativeResult(id, new JSONTokener(result).nextValue(), null); }
                        catch (Exception error) { nativeResult(id, null, "校园页面脚本执行失败"); }
                    });
                    return;
                case "showWindow":
                    showCampus(window);
                    nativeResult(id, true, null);
                    return;
                case "destroyWindow":
                    if (window.view.getParent() == campusOverlay) hideCampus();
                    windows.remove(windowId);
                    if (window.view.getParent() instanceof ViewGroup) ((ViewGroup) window.view.getParent()).removeView(window.view);
                    window.view.destroy();
                    nativeResult(id, true, null);
                    return;
                default: throw new Exception();
            }
        } catch (Exception error) { nativeResult(id, null, "校园窗口不可用，请重新登录"); }
    }
    private void showCampus(CampusWindow window) {
        hideCampus();
        campusOverlay = new LinearLayout(this);
        campusOverlay.setOrientation(LinearLayout.VERTICAL);
        campusOverlay.setBackgroundColor(Color.WHITE);
        Button close = new Button(this);
        close.setText("返回邮学伴");
        close.setOnClickListener(view -> hideCampus());
        campusOverlay.addView(close, new LinearLayout.LayoutParams(-1, -2));
        if (window.view.getParent() instanceof ViewGroup) ((ViewGroup) window.view.getParent()).removeView(window.view);
        campusOverlay.addView(window.view, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(campusOverlay, new FrameLayout.LayoutParams(-1, -1));
    }
    private void hideCampus() {
        if (campusOverlay == null) return;
        for (CampusWindow window : windows.values()) if (window.view != null && window.view.getParent() == campusOverlay) {
            campusOverlay.removeView(window.view);
            root.addView(window.view, 0, new FrameLayout.LayoutParams(-1, -1));
        }
        root.removeView(campusOverlay);
        campusOverlay = null;
    }
    private JSONObject network(String id, JSONObject args) throws Exception {
        String address = args.getString("url");
        String method = args.optString("method", "GET").toUpperCase(Locale.ROOT);
        String body = args.isNull("body") ? null : args.optString("body", null);
        JSONObject headers = args.optJSONObject("headers");
        String initialHost = new URL(address).getHost();
        for (int redirects = 0; redirects < 10; redirects++) {
            URL url = new URL(address);
            boolean campus = campusUrl(address);
            boolean ai = url.getProtocol().equals("https") && url.getHost().equals("api.deepseek.com") &&
                url.getUserInfo() == null && (url.getPort() == -1 || url.getPort() == 443);
            if ((!campus && !ai) || !List.of("GET", "POST", "DELETE").contains(method)) throw new Exception();
            HttpURLConnection connection = (HttpURLConnection) url.openConnection();
            connections.put(id, connection);
            try {
                connection.setConnectTimeout(25_000);
                connection.setReadTimeout(ai ? 120_000 : 25_000);
                connection.setInstanceFollowRedirects(false);
                connection.setRequestMethod(method);
                connection.setRequestProperty("Accept-Encoding", "identity");
                if (headers != null) for (Iterator<String> keys = headers.keys(); keys.hasNext();) {
                    String key = keys.next();
                    if (List.of("host", "connection", "content-length").contains(key.toLowerCase(Locale.ROOT))) continue;
                    if (!url.getHost().equals(initialHost) && (key.equalsIgnoreCase("cookie") || key.equalsIgnoreCase("authorization"))) continue;
                    connection.setRequestProperty(key, headers.getString(key));
                }
                if (campus && (headers == null || !headers.has("cookie") || !url.getHost().equals(initialHost))) {
                    String cookie = android.webkit.CookieManager.getInstance().getCookie(address);
                    if (cookie != null) connection.setRequestProperty("Cookie", cookie);
                }
                if (body != null && !method.equals("GET")) {
                    connection.setDoOutput(true);
                    try (OutputStream output = connection.getOutputStream()) { output.write(body.getBytes(StandardCharsets.UTF_8)); }
                }
                int status = connection.getResponseCode();
                if (campus) for (Map.Entry<String, List<String>> entry : connection.getHeaderFields().entrySet())
                    if ("set-cookie".equalsIgnoreCase(entry.getKey())) for (String cookie : entry.getValue())
                        android.webkit.CookieManager.getInstance().setCookie(address, cookie);
                if (List.of(301, 302, 303, 307, 308).contains(status)) {
                    String location = connection.getHeaderField("Location");
                    if (location == null) throw new Exception();
                    String next = new URL(url, location).toString();
                    if (ai && !new URL(next).getHost().equals(initialHost)) throw new Exception();
                    address = next;
                    if (status == 303 || ((status == 301 || status == 302) && method.equals("POST"))) { method = "GET"; body = null; }
                    continue;
                }
                JSONObject responseHeaders = new JSONObject();
                for (Map.Entry<String, List<String>> entry : connection.getHeaderFields().entrySet())
                    if (entry.getKey() != null && !entry.getKey().equalsIgnoreCase("set-cookie"))
                        responseHeaders.put(entry.getKey(), String.join(", ", entry.getValue()));
                InputStream input = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                if (input != null) try (InputStream stream = input) {
                    byte[] buffer = new byte[8192];
                    int count;
                    while ((count = stream.read(buffer)) != -1) {
                        if (bytes.size() + count > 20_000_000) throw new Exception();
                        bytes.write(buffer, 0, count);
                    }
                }
                return new JSONObject().put("status", status).put("url", address).put("headers", responseHeaders)
                    .put("body", Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP));
            } finally { connections.remove(id); connection.disconnect(); }
        }
        throw new Exception();
    }
    @Override public void onBackPressed() {
        if (campusOverlay != null) { hideCampus(); return; }
        if (ui != null && ui.canGoBack()) { ui.goBack(); return; }
        super.onBackPressed();
    }
    @Override protected void onDestroy() {
        closed = true;
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        for (CampusWindow window : windows.values()) if (window.view != null) window.view.destroy();
        windows.clear();
        if (runtime != null) runtime.destroy();
        if (ui != null) ui.destroy();
        workers.shutdownNow();
        main.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}

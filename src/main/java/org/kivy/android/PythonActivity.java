package org.kivy.android;

import android.os.SystemClock;

import java.io.InputStream;
import java.io.File;
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.ArrayList;

import android.view.ViewGroup;
import android.view.KeyEvent;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.content.Intent;
import android.util.Log;
import android.widget.Toast;
import android.os.AsyncTask;
import android.os.Bundle;
import android.os.PowerManager;
import android.content.Context;
import android.content.pm.PackageManager;
import android.widget.ImageView;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;

import android.widget.AbsoluteLayout;
import android.view.ViewGroup.LayoutParams;

import android.webkit.WebBackForwardList;
import android.webkit.WebChromeClient;
import android.webkit.PermissionRequest;
import android.webkit.WebViewClient;
import android.webkit.WebView;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.os.Environment;         
import android.app.DownloadManager;   
import androidx.core.content.ContextCompat;
import android.os.Build;
import java.util.Arrays;
import android.net.Uri;

import org.renpy.android.ResourceManager;

public class PythonActivity extends Activity {
    // This activity is modified from a mixture of the SDLActivity and
    // PythonActivity in the SDL2 bootstrap, but removing all the SDL2
    // specifics.

    private static final String TAG = "PythonActivity";

    public static PythonActivity mActivity = null;
    public static boolean mOpenExternalLinksInBrowser = false;

    /** If shared libraries (e.g. SDL or the native application) could not be loaded. */
    public static boolean mBrokenLibraries;

    protected static ViewGroup mLayout;
    protected static WebView mWebView;

    protected static Thread mPythonThread;

    private ResourceManager resourceManager = null;
    private Bundle mMetaData = null;
    private PowerManager.WakeLock mWakeLock = null;

    public String getAppRoot() {
        String app_root =  getFilesDir().getAbsolutePath() + "/app";
        return app_root;
    }

    public String getEntryPoint(String search_dir) {
        /* Get the main file (.pyc|.py) depending on if we
         * have a compiled version or not.
        */
        List<String> entryPoints = new ArrayList<String>();
        entryPoints.add("main.pyc");  // python 3 compiled files
        for (String value : entryPoints) {
            File mainFile = new File(search_dir + "/" + value);
            if (mainFile.exists()) {
                return value;
            }
        }
        return "main.py";
    }

    public static void initialize() {
        // The static nature of the singleton and Android quirkyness force us to initialize everything here
        // Otherwise, when exiting the app and returning to it, these variables *keep* their pre exit values
        mWebView = null;
        mLayout = null;
        mBrokenLibraries = false;
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        Log.v(TAG, "My oncreate running");
        resourceManager = new ResourceManager(this);
        super.onCreate(savedInstanceState);

        this.mActivity = this;
        this.showLoadingScreen();
        new UnpackFilesTask().execute(getAppRoot());
    }

    private class UnpackFilesTask extends AsyncTask<String, Void, String> {
        @Override
        protected String doInBackground(String... params) {
            File app_root_file = new File(params[0]);
            Log.v(TAG, "Ready to unpack");
            PythonUtil.unpackAsset(mActivity, "private", app_root_file, true);
            PythonUtil.unpackPyBundle(mActivity, getApplicationInfo().nativeLibraryDir + "/" + "libpybundle", app_root_file, false);
            return null;
        }

        @Override
        protected void onPostExecute(String result) {
            Log.v("Python", "Device: " + android.os.Build.DEVICE);
            Log.v("Python", "Model: " + android.os.Build.MODEL);

            PythonActivity.initialize();

            // Load shared libraries
            String errorMsgBrokenLib = "";
            try {
                loadLibraries();
            } catch(UnsatisfiedLinkError e) {
                System.err.println(e.getMessage());
                mBrokenLibraries = true;
                errorMsgBrokenLib = e.getMessage();
            } catch(Exception e) {
                System.err.println(e.getMessage());
                mBrokenLibraries = true;
                errorMsgBrokenLib = e.getMessage();
            }

            if (mBrokenLibraries)
            {
                AlertDialog.Builder dlgAlert  = new AlertDialog.Builder(PythonActivity.mActivity);
                dlgAlert.setMessage("An error occurred while trying to load the application libraries. Please try again and/or reinstall."
                      + System.getProperty("line.separator")
                      + System.getProperty("line.separator")
                      + "Error: " + errorMsgBrokenLib);
                dlgAlert.setTitle("Python Error");
                dlgAlert.setPositiveButton("Exit",
                    new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface dialog,int id) {
                            // if this button is clicked, close current activity
                            PythonActivity.mActivity.finish();
                        }
                    });
               dlgAlert.setCancelable(false);
               dlgAlert.create().show();

               return;
            }

            // Set up the webview
            String app_root_dir = getAppRoot();

            mWebView = new WebView(PythonActivity.mActivity);
            mWebView.getSettings().setJavaScriptEnabled(true);
            mWebView.getSettings().setDomStorageEnabled(true);
            mWebView.getSettings().setMediaPlaybackRequiresUserGesture(false);
            mWebView.getSettings().setAllowFileAccess(true);
            mWebView.getSettings().setJavaScriptCanOpenWindowsAutomatically(true);
            
            mWebView.loadUrl("file:///android_asset/_load.html");

            mWebView.setLayoutParams(new LayoutParams(LayoutParams.FILL_PARENT, LayoutParams.FILL_PARENT));
            mWebView.setWebViewClient(new WebViewClient() {
                @Override
                public boolean shouldOverrideUrlLoading(WebView view, String url) {
                    Uri u = Uri.parse(url);
                    Log.d(TAG, "WebViewClient shouldOverrideUrlLoading: " + url + " | mOpenExternalLinksInBrowser: " + mOpenExternalLinksInBrowser);

                    String scheme = u.getScheme();
                    String host = u.getHost();

                    // 1. Handle app-specific local URLs (localhost, file assets) - KEEP IN WEBVIEW
                    if ( (scheme != null && scheme.equals("file")) ||
                         (host != null && (host.equals("127.0.0.1") || host.equals("localhost"))) ) {
                        Log.d(TAG, "Letting WebView handle local/internal URL: " + url);
                        return false; // Let WebView handle it
                    }

                    // 2. If mOpenExternalLinksInBrowser is true, open other http/https links externally
                    if (mOpenExternalLinksInBrowser && (scheme != null && (scheme.equals("http") || scheme.equals("https"))) ) {
                        Log.d(TAG, "Opening external link in browser: " + url);
                        try {
                            Intent intent = new Intent(Intent.ACTION_VIEW, u);
                            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); // Good practice for starting activity from non-activity context if needed
                            mActivity.startActivity(intent);
                            return true; // We've handled it
                        } catch (Exception e) {
                            Log.e(TAG, "Could not open external link: " + url, e);
                            Toast.makeText(mActivity, "Could not open link", Toast.LENGTH_SHORT).show();
                            return true; // Still consider it handled to prevent WebView from trying
                        }
                    }
                    
                    // 3. For other schemes (mailto:, tel:, etc.) or if not opening externally
                    //    Try to let the system handle it via an Intent. This can also trigger downloads
                    //    for certain content types if a DownloadManager is not explicitly used.
                    //    However, for robust downloads, DownloadListener is better.
                    try {
                        Log.d(TAG, "Attempting to start activity for non-local/non-http URL: " + url);
                        Intent intent = new Intent(Intent.ACTION_VIEW, u);
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                        // Check if there's an app to handle this intent
                        if (intent.resolveActivity(mActivity.getPackageManager()) != null) {
                            mActivity.startActivity(intent);
                            return true; // We've handled it (or tried to)
                        } else {
                            Log.w(TAG, "No app found to handle URL: " + url);
                            // Fallback to let WebView try, or show an error
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error trying to handle URL with Intent: " + url, e);
                        // Fallback to let WebView try, or show an error
                    }

                    // Default: let WebView try to handle it if nothing else did
                    Log.d(TAG, "Fallback: Letting WebView attempt to handle URL: " + url);
                    return false;
                }

                @Override
                public void onPageFinished(WebView view, String url) {
                    Log.d(TAG, "WebViewClient onPageFinished: " + url);
                    CookieManager.getInstance().flush();
                }
            });

            // *** ADD DOWNLOAD LISTENER FOR PROPER DOWNLOADS ***
            mWebView.setDownloadListener(new DownloadListener() {
                @Override
                public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimetype, long contentLength) {
                    Log.d(TAG, "Download started via DownloadListener. URL: " + url + " Mimetype: " + mimetype);
                    try {
                        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                        request.setMimeType(mimetype);
                        // Use "Content-Disposition" to get filename if available
                        String cookies = CookieManager.getInstance().getCookie(url);
                        request.addRequestHeader("cookie", cookies);
                        request.addRequestHeader("User-Agent", userAgent);
                        request.setDescription("Downloading file...");
                        
                        // Try to get filename from content-disposition
                        String fileName = android.webkit.URLUtil.guessFileName(url, contentDisposition, mimetype);
                        request.setTitle(fileName);
                        
                        request.allowScanningByMediaScanner();
                        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                        request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);
                        
                        DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                        if (dm != null) {
                            dm.enqueue(request);
                            Toast.makeText(getApplicationContext(), "Downloading " + fileName, Toast.LENGTH_LONG).show();
                        } else {
                            Log.e(TAG, "DownloadManager is null");
                            Toast.makeText(getApplicationContext(), "Download failed: DownloadManager unavailable.", Toast.LENGTH_LONG).show();
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error starting download: " + e.getMessage());
                        Toast.makeText(getApplicationContext(), "Download failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                        // Optionally, try to open the URL in an external browser as a fallback for download
                        try {
                            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                            mActivity.startActivity(i);
                        } catch (Exception ex) {
                            Log.e(TAG, "Fallback to external browser for download failed: " + ex.getMessage());
                        }
                    }
                }
            });

            // *** ADD CUSTOM WEBCHROMECLIENT HERE ***
            mWebView.setWebChromeClient(new WebChromeClient() {
                @Override
                public void onPermissionRequest(final PermissionRequest request) {
                    final String[] requestedResources = request.getResources();
                    Log.d(TAG, "WebChromeClient: onPermissionRequest for origin: " + request.getOrigin().toString());
                    Log.d(TAG, "WebChromeClient: Requesting resources: " + Arrays.toString(requestedResources));

                    mActivity.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            boolean cameraRequested = false;
                            boolean microphoneRequested = false;
                            // Add flags for other resources if needed

                            for (String resource : requestedResources) {
                                if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) {
                                    cameraRequested = true;
                                } else if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) {
                                    microphoneRequested = true;
                                }
                                // Check for other resources...
                            }

                            ArrayList<String> permissionsToGrantInWebView = new ArrayList<>();
                            boolean allAppPermissionsGranted = true;

                            if (cameraRequested) {
                                if (ContextCompat.checkSelfPermission(mActivity, android.Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                                    permissionsToGrantInWebView.add(PermissionRequest.RESOURCE_VIDEO_CAPTURE);
                                } else {
                                    Log.w(TAG, "App lacks CAMERA permission for WebView request.");
                                    allAppPermissionsGranted = false;
                                }
                            }

                            if (microphoneRequested) {
                                // IMPORTANT: You would also need to add Permission.RECORD_AUDIO to your Python main.py
                                // permissions_list AND <uses-permission android:name="android.permission.RECORD_AUDIO" />
                                // to your AndroidManifest.xml if you haven't already (you have for RECORD_AUDIO but maybe not specifically for webview mic access).
                                if (ContextCompat.checkSelfPermission(mActivity, android.Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                                    permissionsToGrantInWebView.add(PermissionRequest.RESOURCE_AUDIO_CAPTURE);
                                } else {
                                    Log.w(TAG, "App lacks RECORD_AUDIO permission for WebView request.");
                                    allAppPermissionsGranted = false;
                                }
                            }

                            // Handle other requested resources similarly...

                            if (!permissionsToGrantInWebView.isEmpty() && allAppPermissionsGranted) {
                                // Grant only the resources for which the app has permission and were requested
                                Log.i(TAG, "Granting WebView permissions for: " + permissionsToGrantInWebView.toString());
                                request.grant(permissionsToGrantInWebView.toArray(new String[0]));
                            } else if (!permissionsToGrantInWebView.isEmpty() && !allAppPermissionsGranted) {
                                // Some app-level permissions were missing for requested webview resources
                                Log.w(TAG, "Denying WebView request because some app-level permissions are missing for: " + Arrays.toString(requestedResources) +
                                        ". Specifically granting only for: " + permissionsToGrantInWebView.toString() + " if any, but overall one was missing.");
                                // You might choose to grant the subset for which app has permission, or deny all if one is missing.
                                // For simplicity, if any *requested* app-level perm is missing, deny the whole webview request:
                                request.deny();
                            }
                            else {
                                // No relevant resources requested or no app permissions for them
                                Log.d(TAG, "Denying WebView request for unhandled or unpermitted resources: " + Arrays.toString(requestedResources));
                                request.deny();
                            }
                        }
                    });
                }


            mLayout = new AbsoluteLayout(PythonActivity.mActivity);
            mLayout.addView(mWebView);

            setContentView(mLayout);

            String mFilesDirectory = mActivity.getFilesDir().getAbsolutePath();
            String entry_point = getEntryPoint(app_root_dir);

            Log.v(TAG, "Setting env vars for start.c and Python to use");
            PythonActivity.nativeSetenv("ANDROID_ENTRYPOINT", entry_point);
            PythonActivity.nativeSetenv("ANDROID_ARGUMENT", app_root_dir);
            PythonActivity.nativeSetenv("ANDROID_APP_PATH", app_root_dir);
            PythonActivity.nativeSetenv("ANDROID_PRIVATE", mFilesDirectory);
            PythonActivity.nativeSetenv("ANDROID_UNPACK", app_root_dir);
            PythonActivity.nativeSetenv("PYTHONHOME", app_root_dir);
            PythonActivity.nativeSetenv("PYTHONPATH", app_root_dir + ":" + app_root_dir + "/lib");
            PythonActivity.nativeSetenv("PYTHONOPTIMIZE", "2");

            try {
                Log.v(TAG, "Access to our meta-data...");
                mActivity.mMetaData = mActivity.getPackageManager().getApplicationInfo(
                        mActivity.getPackageName(), PackageManager.GET_META_DATA).metaData;

                PowerManager pm = (PowerManager) mActivity.getSystemService(Context.POWER_SERVICE);
                if ( mActivity.mMetaData.getInt("wakelock") == 1 ) {
                    mActivity.mWakeLock = pm.newWakeLock(PowerManager.SCREEN_BRIGHT_WAKE_LOCK, "Screen On");
                    mActivity.mWakeLock.acquire();
                }
            } catch (PackageManager.NameNotFoundException e) {
            }

            final Thread pythonThread = new Thread(new PythonMain(), "PythonThread");
            PythonActivity.mPythonThread = pythonThread;
            pythonThread.start();

            final Thread wvThread = new Thread(new WebViewLoaderMain(), "WvThread");
            wvThread.start();
        }
    }

    @Override
    public void onDestroy() {
        Log.i("Destroy", "end of app");
        super.onDestroy();

        // make sure all child threads (python_thread) are stopped
        android.os.Process.killProcess(android.os.Process.myPid());
    }

    public void loadLibraries() {
        String app_root = new String(getAppRoot());
        File app_root_file = new File(app_root);
        PythonUtil.loadLibraries(app_root_file,
            new File(getApplicationInfo().nativeLibraryDir));
    }

    public static void loadUrl(String url) {
        class LoadUrl implements Runnable {
            private String mUrl;

            public LoadUrl(String url) {
                mUrl = url;
            }

            public void run() {
                mWebView.loadUrl(mUrl);
            }
        }

        Log.i(TAG, "Opening URL: " + url);
        mActivity.runOnUiThread(new LoadUrl(url));
    }

    public static void enableZoom() {
        mActivity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                mWebView.getSettings().setBuiltInZoomControls(true);
                mWebView.getSettings().setDisplayZoomControls(false);
            }
        });
    }

    public static ViewGroup getLayout() {
        return   mLayout;
    }

    long lastBackClick = 0;
    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        // Check if the key event was the Back button
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            // Go back if there is web page history behind,
            // but not to the start preloader
            WebBackForwardList webViewBackForwardList = mWebView.copyBackForwardList();
            if (webViewBackForwardList.getCurrentIndex() > 1) {
                mWebView.goBack();
                return true;
            }

            // If there's no web page history, bubble up to the default
            // system behavior (probably exit the activity)
            if (SystemClock.elapsedRealtime() - lastBackClick > 2000){
                lastBackClick = SystemClock.elapsedRealtime();
                Toast.makeText(this, "Tap again to close the app", Toast.LENGTH_LONG).show();
                return true;
            }

            lastBackClick = SystemClock.elapsedRealtime();
        }

        return super.onKeyDown(keyCode, event);
    }

    // loading screen implementation
    public static ImageView mImageView = null;
    public void removeLoadingScreen() {
      runOnUiThread(new Runnable() {
        public void run() {
          if (PythonActivity.mImageView != null &&
                  PythonActivity.mImageView.getParent() != null) {
            ((ViewGroup)PythonActivity.mImageView.getParent()).removeView(
            PythonActivity.mImageView);
            PythonActivity.mImageView = null;
          }
        }
      });
    }

    protected void showLoadingScreen() {
      // load the bitmap
      // 1. if the image is valid and we don't have layout yet, assign this bitmap
      // as main view.
      // 2. if we have a layout, just set it in the layout.
      // 3. If we have an mImageView already, then do nothing because it will have
      // already been made the content view or added to the layout.

      if (mImageView == null) {
        int presplashId = this.resourceManager.getIdentifier("presplash", "drawable");
        InputStream is = this.getResources().openRawResource(presplashId);
        Bitmap bitmap = null;
        try {
          bitmap = BitmapFactory.decodeStream(is);
        } finally {
          try {
            is.close();
          } catch (IOException e) {};
        }

        mImageView = new ImageView(this);
        mImageView.setImageBitmap(bitmap);

        /*
         * Set the presplash loading screen background color
         * https://developer.android.com/reference/android/graphics/Color.html
         * Parse the color string, and return the corresponding color-int.
         * If the string cannot be parsed, throws an IllegalArgumentException exception.
         * Supported formats are: #RRGGBB #AARRGGBB or one of the following names:
         * 'red', 'blue', 'green', 'black', 'white', 'gray', 'cyan', 'magenta', 'yellow',
         * 'lightgray', 'darkgray', 'grey', 'lightgrey', 'darkgrey', 'aqua', 'fuchsia',
         * 'lime', 'maroon', 'navy', 'olive', 'purple', 'silver', 'teal'.
         */
        String backgroundColor = resourceManager.getString("presplash_color");
        if (backgroundColor != null) {
          try {
            mImageView.setBackgroundColor(Color.parseColor(backgroundColor));
          } catch (IllegalArgumentException e) {}
        }
        mImageView.setLayoutParams(new ViewGroup.LayoutParams(
        ViewGroup.LayoutParams.FILL_PARENT,
        ViewGroup.LayoutParams.FILL_PARENT));
        mImageView.setScaleType(ImageView.ScaleType.FIT_CENTER);

      }

      if (mLayout == null) {
        setContentView(mImageView);
      } else if (PythonActivity.mImageView.getParent() == null){
        mLayout.addView(mImageView);
      }
    }

    //----------------------------------------------------------------------------
    // Listener interface for onNewIntent
    //

    public interface NewIntentListener {
        void onNewIntent(Intent intent);
    }

    private List<NewIntentListener> newIntentListeners = null;

    public void registerNewIntentListener(NewIntentListener listener) {
        if ( this.newIntentListeners == null )
            this.newIntentListeners = Collections.synchronizedList(new ArrayList<NewIntentListener>());
        this.newIntentListeners.add(listener);
    }

    public void unregisterNewIntentListener(NewIntentListener listener) {
        if ( this.newIntentListeners == null )
            return;
        this.newIntentListeners.remove(listener);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        if ( this.newIntentListeners == null )
            return;
        this.onResume();
        synchronized ( this.newIntentListeners ) {
            Iterator<NewIntentListener> iterator = this.newIntentListeners.iterator();
            while ( iterator.hasNext() ) {
                (iterator.next()).onNewIntent(intent);
            }
        }
    }

    //----------------------------------------------------------------------------
    // Listener interface for onActivityResult
    //

    public interface ActivityResultListener {
        void onActivityResult(int requestCode, int resultCode, Intent data);
    }

    private List<ActivityResultListener> activityResultListeners = null;

    public void registerActivityResultListener(ActivityResultListener listener) {
        if ( this.activityResultListeners == null )
            this.activityResultListeners = Collections.synchronizedList(new ArrayList<ActivityResultListener>());
        this.activityResultListeners.add(listener);
    }

    public void unregisterActivityResultListener(ActivityResultListener listener) {
        if ( this.activityResultListeners == null )
            return;
        this.activityResultListeners.remove(listener);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent intent) {
        if ( this.activityResultListeners == null )
            return;
        this.onResume();
        synchronized ( this.activityResultListeners ) {
            Iterator<ActivityResultListener> iterator = this.activityResultListeners.iterator();
            while ( iterator.hasNext() )
                (iterator.next()).onActivityResult(requestCode, resultCode, intent);
        }
    }

    public static void start_service(
            String serviceTitle,
            String serviceDescription,
            String pythonServiceArgument
            ) {
        _do_start_service(
            serviceTitle, serviceDescription, pythonServiceArgument, true
        );
    }

    public static void start_service_not_as_foreground(
            String serviceTitle,
            String serviceDescription,
            String pythonServiceArgument
            ) {
        _do_start_service(
            serviceTitle, serviceDescription, pythonServiceArgument, false
        );
    }

    public static void _do_start_service(
            String serviceTitle,
            String serviceDescription,
            String pythonServiceArgument,
            boolean showForegroundNotification
            ) {
        Intent serviceIntent = new Intent(PythonActivity.mActivity, PythonService.class);
        String argument = PythonActivity.mActivity.getFilesDir().getAbsolutePath();
        String app_root_dir = PythonActivity.mActivity.getAppRoot();
        String entry_point = PythonActivity.mActivity.getEntryPoint(app_root_dir + "/service");
        serviceIntent.putExtra("androidPrivate", argument);
        serviceIntent.putExtra("androidArgument", app_root_dir);
        serviceIntent.putExtra("serviceEntrypoint", "service/" + entry_point);
        serviceIntent.putExtra("pythonName", "python");
        serviceIntent.putExtra("pythonHome", app_root_dir);
        serviceIntent.putExtra("pythonPath", app_root_dir + ":" + app_root_dir + "/lib");
        serviceIntent.putExtra("serviceStartAsForeground",
            (showForegroundNotification ? "true" : "false")
        );
        serviceIntent.putExtra("serviceTitle", serviceTitle);
        serviceIntent.putExtra("serviceDescription", serviceDescription);
        serviceIntent.putExtra("pythonServiceArgument", pythonServiceArgument);
        PythonActivity.mActivity.startService(serviceIntent);
    }

    public static void stop_service() {
        Intent serviceIntent = new Intent(PythonActivity.mActivity, PythonService.class);
        PythonActivity.mActivity.stopService(serviceIntent);
    }


    public static native void nativeSetenv(String name, String value);
    public static native int nativeInit(Object arguments);


    /**
     * Used by android.permissions p4a module to register a call back after
     * requesting runtime permissions
     **/
    public interface PermissionsCallback {
        void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults);
    }

    private PermissionsCallback permissionCallback;
    private boolean havePermissionsCallback = false;

    public void addPermissionsCallback(PermissionsCallback callback) {
        permissionCallback = callback;
        havePermissionsCallback = true;
        Log.v(TAG, "addPermissionsCallback(): Added callback for onRequestPermissionsResult");
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        Log.v(TAG, "onRequestPermissionsResult()");
        if (havePermissionsCallback) {
            Log.v(TAG, "onRequestPermissionsResult passed to callback");
            permissionCallback.onRequestPermissionsResult(requestCode, permissions, grantResults);
        }
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
    }

    /**
     * Used by android.permissions p4a module to check a permission
     **/
    public boolean checkCurrentPermission(String permission) {
        if (android.os.Build.VERSION.SDK_INT < 23)
            return true;

        try {
            java.lang.reflect.Method methodCheckPermission =
                Activity.class.getMethod("checkSelfPermission", String.class);
            Object resultObj = methodCheckPermission.invoke(this, permission);
            int result = Integer.parseInt(resultObj.toString());
            if (result == PackageManager.PERMISSION_GRANTED)
                return true;
        } catch (IllegalAccessException | NoSuchMethodException |
                 InvocationTargetException e) {
        }
        return false;
    }

    /**
     * Used by android.permissions p4a module to request runtime permissions
     **/
    public void requestPermissionsWithRequestCode(String[] permissions, int requestCode) {
        if (android.os.Build.VERSION.SDK_INT < 23)
            return;
        try {
            java.lang.reflect.Method methodRequestPermission =
                Activity.class.getMethod("requestPermissions",
                String[].class, int.class);
            methodRequestPermission.invoke(this, permissions, requestCode);
        } catch (IllegalAccessException | NoSuchMethodException |
                 InvocationTargetException e) {
        }
    }

    public void requestPermissions(String[] permissions) {
        requestPermissionsWithRequestCode(permissions, 1);
    }
}


class PythonMain implements Runnable {
    @Override
    public void run() {
        PythonActivity.nativeInit(new String[0]);
    }
}

class WebViewLoaderMain implements Runnable {
    @Override
    public void run() {
        WebViewLoader.testConnection();
    }
}
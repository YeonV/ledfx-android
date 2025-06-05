// src/main/java/com/ledfx/ledfx/LedFxActivity.java
package com.ledfx.ledfx; // Your app's package

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.AsyncTask; // If you need to replicate or call UnpackFilesTask from super
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.util.Log;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.app.DownloadManager;
import android.widget.Toast;
import androidx.core.content.ContextCompat;

import org.kivy.android.PythonActivity; // Import P4A's PythonActivity
// Import PythonUtil if needed, or rely on super class's usage
// import org.kivy.android.PythonUtil;

import java.util.Arrays;
import java.util.ArrayList; // For onPermissionRequest logic

public class LedFxActivity extends PythonActivity { // Extend P4A's PythonActivity
    private static final String TAG = "LedFxActivity"; // New TAG for your activity

    // We will get mWebView from the superclass or find it if PythonActivity makes it accessible.
    // PythonActivity.mWebView is protected static, so we should be able to access it.

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        Log.d(TAG, "LedFxActivity onCreate called");
        super.onCreate(savedInstanceState); // CRUCIAL: Call super.onCreate() FIRST

        // After super.onCreate(), P4A's PythonActivity will have done much of its setup,
        // including potentially creating mLayout and mWebView (especially after UnpackFilesTask).
        // We need to ensure mWebView is available before trying to set clients on it.

        // The original PythonActivity creates mWebView in onPostExecute of UnpackFilesTask.
        // This means we can't just set the WebChromeClient directly in *this* onCreate
        // because mWebView might not exist yet.

        // Option 1: Hope mWebView is ready after super.onCreate() if UnpackFilesTask is synchronous enough
        // This is less reliable.

        // Option 2 (Better): We need a way to hook in *after* P4A's PythonActivity
        // has created its mWebView.
        // One way is to override a method that P4A's PythonActivity calls *after*
        // mWebView is set up, or by observing the view hierarchy.

        // Let's try a slightly different approach:
        // We know that P4A's PythonActivity has a static `mWebView` field.
        // We can attempt to set the clients after a short delay or in onResume,
        // or more robustly, by creating a new UnpackFilesTask that calls super's
        // and then does our setup.
        // However, the simplest for now is to assume that after super.onCreate() and
        // its async UnpackFilesTask completes, our Python logic (main.py)
        // will run, and *then* the WebViewLoader will load the actual URL.
        // The permission request will only happen *after* our React app loads and tries to use the camera.

        // So, the WebChromeClient and DownloadListener should be set on PythonActivity.mWebView.
        // Let's try setting it up in a way that it applies to the static mWebView.
        // The risk is if PythonActivity.mWebView is reassigned.
        // A robust way is to ensure this runs after onPostExecute in the original PythonActivity.
        // Since we are extending, we can override onPostExecute of a *new* UnpackFilesTask
        // or find another hook.

        // For now, let's assume P4A's PythonActivity.mWebView will be the one used.
        // We can try to apply this in onWindowFocusChanged or similar late-stage callback.
    }


    // This method is called when the Activity gains or loses focus.
    // It's often called after UI elements are created and attached.
    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        Log.d(TAG, "onWindowFocusChanged, hasFocus: " + hasFocus);
        if (hasFocus && PythonActivity.mWebView != null && PythonActivity.mWebView.getWebChromeClient().getClass() == WebChromeClient.class) {
            // Check if mWebView exists and if a custom client hasn't been set yet
            // (The default client is just `new WebChromeClient()`)
            Log.i(TAG, "Setting custom WebChromeClient and DownloadListener now.");
            
            // Apply Download Listener
            PythonActivity.mWebView.setDownloadListener(new DownloadListener() {
                @Override
                public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimetype, long contentLength) {
                    Log.d(TAG, "Download started. URL: " + url + " Mimetype: " + mimetype);
                    try {
                        DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                        request.setMimeType(mimetype);
                        String cookies = CookieManager.getInstance().getCookie(url);
                        request.addRequestHeader("cookie", cookies);
                        request.addRequestHeader("User-Agent", userAgent);
                        request.setDescription("Downloading file...");
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
                            Toast.makeText(getApplicationContext(), "Download failed: DM unavailable.", Toast.LENGTH_LONG).show();
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error starting download: " + e.getMessage());
                        Toast.makeText(getApplicationContext(), "Download error: " + e.getMessage(), Toast.LENGTH_LONG).show();
                        try {
                            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                            startActivity(i); // Use 'startActivity' as we are in an Activity context
                        } catch (Exception ex) {
                            Log.e(TAG, "Fallback download failed: " + ex.getMessage());
                        }
                    }
                }
            });

            // Apply Custom WebChromeClient for Permissions
            PythonActivity.mWebView.setWebChromeClient(new WebChromeClient() {
                @Override
                public void onPermissionRequest(final PermissionRequest request) {
                    final String[] requestedResources = request.getResources();
                    Log.d(TAG, "LedFxActivity WebChromeClient: onPermissionRequest for origin: " + request.getOrigin().toString());
                    Log.d(TAG, "LedFxActivity WebChromeClient: Requesting resources: " + Arrays.toString(requestedResources));

                    // final Activity activity = LedFxActivity.this; // Use 'this' or PythonActivity.mActivity
                    // PythonActivity.mActivity should be correctly set by super.onCreate()
                    
                    final Activity currentActivity = PythonActivity.mActivity; // Or just LedFxActivity.this

                    currentActivity.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            boolean cameraRequested = false;
                            boolean microphoneRequested = false;

                            for (String resource : requestedResources) {
                                if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) {
                                    cameraRequested = true;
                                } else if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) {
                                    microphoneRequested = true;
                                }
                            }

                            ArrayList<String> permissionsToGrantInWebView = new ArrayList<>();
                            boolean allAppPermissionsGranted = true;

                            if (cameraRequested) {
                                if (ContextCompat.checkSelfPermission(currentActivity, android.Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                                    permissionsToGrantInWebView.add(PermissionRequest.RESOURCE_VIDEO_CAPTURE);
                                } else {
                                    Log.w(TAG, "App lacks CAMERA permission for WebView request.");
                                    allAppPermissionsGranted = false;
                                }
                            }

                            if (microphoneRequested) {
                                if (ContextCompat.checkSelfPermission(currentActivity, android.Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                                    permissionsToGrantInWebView.add(PermissionRequest.RESOURCE_AUDIO_CAPTURE);
                                } else {
                                    Log.w(TAG, "App lacks RECORD_AUDIO permission for WebView request.");
                                    allAppPermissionsGranted = false;
                                }
                            }

                            if (!permissionsToGrantInWebView.isEmpty() && allAppPermissionsGranted) {
                                Log.i(TAG, "Granting WebView permissions for: " + permissionsToGrantInWebView.toString());
                                request.grant(permissionsToGrantInWebView.toArray(new String[0]));
                            } else if (!permissionsToGrantInWebView.isEmpty() && !allAppPermissionsGranted) {
                                Log.w(TAG, "Denying WebView req: missing app-level perms for: " + Arrays.toString(requestedResources));
                                request.deny();
                            } else {
                                Log.d(TAG, "Denying WebView req: unhandled/unpermitted resources: " + Arrays.toString(requestedResources));
                                request.deny();
                            }
                        }
                    });
                }
                // You can override other WebChromeClient methods here if needed, calling super.methodName(...)
            });
            Log.i(TAG, "Custom WebChromeClient and DownloadListener have been set.");
        } else if (hasFocus && PythonActivity.mWebView != null) {
            Log.d(TAG, "WebChromeClient might already be custom or mWebView not ready for new client.");
        }
    }

    // You generally do NOT need to re-implement all methods of PythonActivity
    // unless you specifically want to change their behavior.
    // For example, you don't need to copy getAppRoot, initialize, UnpackFilesTask, etc.,
    // as super.onCreate() will call P4A's PythonActivity versions of these.
    // Our goal is just to hook into the lifecycle at the right point to modify mWebView.
}
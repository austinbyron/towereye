"""macOS camera permission. OpenCV opens AVFoundation devices without ever
asking, so a process spawned by an app that was never granted access just
fails to open every camera. Ask up front, and say so when denied."""
import sys
import threading
import time

_keep = []  # completion blocks must outlive the XPC reply that releases them

DENIED_HINT = (
    "camera access is denied for this app. Allow it under System Settings → "
    "Privacy & Security → Camera (the app that launched towereye, e.g. towereye.app "
    "or your terminal), then try again."
)


def ensure_camera_access(timeout: float = 60.0, log=print) -> bool:
    """True when we may open cameras. On macOS this triggers the permission
    prompt if the responsible app has never been asked."""
    if sys.platform != "darwin":
        return True
    try:
        import AVFoundation as av
    except ImportError:
        return True  # can't check; let OpenCV try
    status = av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo)
    if status == 3:  # authorized
        return True
    if status == 0:  # not determined: ask, and wait for the user
        done = threading.Event()
        result = {"granted": False}

        def handler(granted):
            result["granted"] = bool(granted)
            done.set()

        log("asking macOS for camera access...")
        _keep.append(handler)
        av.AVCaptureDevice.requestAccessForMediaType_completionHandler_(av.AVMediaTypeVideo, handler)
        done.wait(timeout)
        # the reply block is disposed on a dispatch thread right after the
        # handler runs; give it a beat so it never races interpreter shutdown
        time.sleep(0.3)
        if result["granted"]:
            return True
    log(DENIED_HINT)
    return False

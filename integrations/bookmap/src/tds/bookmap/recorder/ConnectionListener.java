package tds.bookmap.recorder;

import velox.api.layer1.Layer1ApiAdminListener;
import velox.api.layer1.data.DisconnectionReason;
import velox.api.layer1.data.LoginFailedReason;
import velox.api.layer1.data.SystemTextMessageType;

/**
 * Admin callbacks become enumerated states only (BMREC-06). No argument of any callback is read, logged,
 * forwarded or toString()-ed: reasons, texts and user-message objects may carry account or login text.
 */
final class ConnectionListener implements Layer1ApiAdminListener {
    private final Capture capture;

    ConnectionListener(Capture capture) {
        this.capture = capture;
    }

    @Override
    public void onLoginFailed(LoginFailedReason reason, String message) {
        capture.connection(Frames.CONN_LOGIN_FAILED);
    }

    @Override
    public void onLoginSuccessful() {
        capture.connection(Frames.CONN_LOGIN_SUCCESSFUL);
    }

    @Override
    public void onConnectionLost(DisconnectionReason reason, String message) {
        capture.connection(Frames.CONN_LOST);
    }

    @Override
    public void onConnectionRestored() {
        capture.connection(Frames.CONN_RESTORED);
    }

    @Override
    public void onSystemTextMessage(String message, SystemTextMessageType type) {
        capture.ignoredAdminMessage();
    }

    @Override
    public void onUserMessage(Object data) {
        capture.ignoredAdminMessage();
    }
}

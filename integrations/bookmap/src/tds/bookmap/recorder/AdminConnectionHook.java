package tds.bookmap.recorder;

import velox.api.layer1.Layer1ApiProvider;
import velox.api.layer1.simplified.Api;

/**
 * THE audited getProvider site (BMREC-02). This is the only invocation of {@code Api.getProvider()} in the jar,
 * and its result is used for exactly one thing: as the receiver of {@code addListener}/{@code removeListener}
 * with a {@code Layer1ApiAdminListener} argument. It is kept in a local variable only: never stored in a field,
 * returned, passed as an argument or cast. The build's bytecode allowlist check (integrations/bookmap/tools/
 * allowlist_check.py) enforces all of this on the final jar.
 */
final class AdminConnectionHook {
    private AdminConnectionHook() {
    }

    static void apply(Api api, ConnectionListener listener, boolean register) {
        Layer1ApiProvider provider = api.getProvider();
        if (register) {
            provider.addListener(listener);
        } else {
            provider.removeListener(listener);
        }
    }
}

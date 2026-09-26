import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import velox.api.layer1.Layer1ApiAdminListener;
import velox.api.layer1.Layer1ApiProvider;
import velox.api.layer1.data.InstrumentInfo;
import velox.api.layer1.data.TradeInfo;
import velox.api.layer1.simplified.Api;
import velox.api.layer1.simplified.InitialState;
import tds.bookmap.recorder.RecorderModule;

/**
 * TEST-ONLY fake Bookmap host (never packaged, never checked by the allowlist, never loaded into Bookmap).
 * Drives the REAL built add-on jar through its public callbacks so the end-to-end test exercises the real Java
 * encoder, the real bounded queue and forwarder, the real named pipe and the real Python recorder.
 *
 * Uses java.lang.reflect.Proxy to stand in for Bookmap's Api and provider: this is exactly the kind of dynamic
 * code the add-on itself is forbidden to contain (BMREC-03), which is why it lives here and not in src/.
 */
public final class E2EHarness {
    public static void main(String[] args) throws Exception {
        List<Layer1ApiAdminListener> admin = new ArrayList<>();
        Layer1ApiProvider provider = (Layer1ApiProvider) Proxy.newProxyInstance(
                E2EHarness.class.getClassLoader(), new Class<?>[] {Layer1ApiProvider.class},
                (p, m, a) -> {
                    if (m.getName().equals("addListener") && a[0] instanceof Layer1ApiAdminListener) {
                        admin.add((Layer1ApiAdminListener) a[0]);
                    } else if (m.getName().equals("removeListener") && a[0] instanceof Layer1ApiAdminListener) {
                        admin.remove(a[0]);
                    } else if (!m.getName().equals("hashCode") && !m.getName().equals("equals")) {
                        throw new IllegalStateException("add-on called provider." + m.getName());
                    }
                    return m.getName().equals("hashCode") ? Integer.valueOf(1) : null;
                });
        Api api = (Api) Proxy.newProxyInstance(E2EHarness.class.getClassLoader(), new Class<?>[] {Api.class},
                (p, m, a) -> {
                    if (m.getName().equals("getProvider")) {
                        return provider;
                    }
                    throw new IllegalStateException("add-on called Api." + m.getName());
                });
        InstrumentInfo info = new InstrumentInfo("BTCUSDT", "BNF", "crypto", 0.1, 1.0, "BTCUSDT@BNF", true, 1000.0,
                true);
        RecorderModule mod = new RecorderModule();
        long t = System.currentTimeMillis() * 1_000_000L;
        mod.initialize("BTCUSDT@BNF", info, api, new InitialState());
        if (admin.size() != 1) {
            throw new IllegalStateException("expected one admin listener, got " + admin.size());
        }
        if (args.length > 0 && args[0].equals("overflow")) {
            overflow(mod);
            return;
        }
        Thread.sleep(1500); // let the forwarder connect (backoff starts at 250 ms)

        // historical snapshot: 5 bid + 5 ask levels around 65000.0 (level 650000 at pips 0.1)
        mod.onTimestamp(t);
        for (int i = 1; i <= 5; i++) {
            mod.onDepth(true, 650000 - i, 1000 * i);
            mod.onDepth(false, 650000 + i, 1000 * i);
        }
        mod.onSnapshotEnd();
        mod.onRealtimeStart();
        for (int k = 0; k < 200; k++) {
            t = System.currentTimeMillis() * 1_000_000L;
            mod.onTimestamp(t);
            mod.onDepth(k % 2 == 0, k % 2 == 0 ? 650000 - 1 - (k % 5) : 650000 + 1 + (k % 5), 500 + k);
            if (k % 10 == 0) {
                mod.onTrade(650000.0 + (k % 2 == 0 ? 1 : -1), 3 + k, new TradeInfo(false, k % 20 == 0));
            }
            Thread.sleep(5);
        }
        // connection loss/restore, then Bookmap re-sends a snapshot (as the recorder requires, contract §5)
        admin.get(0).onConnectionLost(null, "marker-should-never-appear-in-output");
        admin.get(0).onSystemTextMessage("marker-should-never-appear-in-output", null);
        admin.get(0).onConnectionRestored();
        mod.onSnapshotEnd();
        for (int k = 0; k < 50; k++) {
            mod.onTimestamp(System.currentTimeMillis() * 1_000_000L);
            mod.onDepth(true, 650000 - 1, 700 + k);
            Thread.sleep(5);
        }
        Thread.sleep(2500); // at least two timer heartbeats with a quiet market
        long s0 = System.nanoTime();
        mod.stop();
        long stopMs = (System.nanoTime() - s0) / 1_000_000L;
        System.out.println("E2E harness: stop() returned in " + stopMs + " ms; admin listeners left: "
                + admin.size());
        if (stopMs > 2500 || !admin.isEmpty()) {
            System.exit(3);
        }
    }

    /**
     * BMREC-17 scenario: the recorder is NOT running while 70 000 depth callbacks arrive, so the bounded queue
     * (65 536) overflows. Every callback must return immediately (never wait on the pipe), and when the recorder
     * comes up the drops must surface as a GAP followed by a book checkpoint.
     */
    private static void overflow(RecorderModule mod) throws Exception {
        mod.onTimestamp(System.currentTimeMillis() * 1_000_000L);
        mod.onSnapshotEnd();
        mod.onRealtimeStart();
        long maxNs = 0L;
        for (int k = 0; k < 70_000; k++) {
            long a = System.nanoTime();
            mod.onDepth(true, 650000 - 1 - (k % 5), 1 + k);
            long d = System.nanoTime() - a;
            if (d > maxNs) {
                maxNs = d;
            }
        }
        System.out.println("OVERFLOWED maxCallbackMs=" + (maxNs / 1_000_000.0));
        System.out.flush();
        Thread.sleep(20_000); // the test starts the recorder now; the forwarder reconnects within its backoff
        long s0 = System.nanoTime();
        mod.stop();
        System.out.println("E2E overflow harness: stop() returned in " + (System.nanoTime() - s0) / 1_000_000L
                + " ms");
    }
}

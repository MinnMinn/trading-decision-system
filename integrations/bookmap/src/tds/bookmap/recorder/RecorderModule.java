package tds.bookmap.recorder;

import java.util.concurrent.atomic.AtomicBoolean;
import velox.api.layer1.annotations.Layer1ApiVersion;
import velox.api.layer1.annotations.Layer1ApiVersionValue;
import velox.api.layer1.annotations.Layer1SimpleAttachable;
import velox.api.layer1.annotations.Layer1StrategyName;
import velox.api.layer1.data.InstrumentInfo;
import velox.api.layer1.data.TradeInfo;
import velox.api.layer1.simplified.Api;
import velox.api.layer1.simplified.CustomModule;
import velox.api.layer1.simplified.DepthDataListener;
import velox.api.layer1.simplified.HistoricalModeListener;
import velox.api.layer1.simplified.InitialState;
import velox.api.layer1.simplified.SnapshotEndListener;
import velox.api.layer1.simplified.TimeListener;
import velox.api.layer1.simplified.TradeDataListener;

/**
 * Stage H1 read-only recorder add-on (docs/plans/2026-09-26-heatmap-realtime-plan.md, stage H1).
 *
 * Captures depth, trades (with aggressor), Bookmap time, the HISTORICAL->LIVE boundary, snapshot end, connection
 * events and InstrumentInfo, and forwards them one-way to the Python recorder's named pipe. It computes no trading
 * feature, places no order, makes no network call and writes no file (plan §1.8; BMREC-01..06).
 *
 * One instrument per JVM: H1's pipe has exactly one instance (BMREC-11), so a second enabled instance stays inert
 * instead of competing for the pipe.
 */
@Layer1SimpleAttachable
@Layer1StrategyName("TDS H1 Recorder (read-only)")
@Layer1ApiVersion(Layer1ApiVersionValue.VERSION3)
public final class RecorderModule implements CustomModule, DepthDataListener, TradeDataListener, TimeListener,
        HistoricalModeListener, SnapshotEndListener {

    private static final AtomicBoolean ACTIVE = new AtomicBoolean(false);

    private volatile boolean owner;
    private Api api;
    private Capture capture;
    private ConnectionListener connectionListener;
    private boolean monitorRegistered;
    private Forwarder forwarder;

    @Override
    public void initialize(String alias, InstrumentInfo info, Api api, InitialState initialState) {
        if (!ACTIVE.compareAndSet(false, true)) {
            return; // inert: another instrument already owns the recorder pipe in this JVM
        }
        owner = true;
        this.api = api;
        capture = new Capture(Frames.QUEUE_CAPACITY);
        connectionListener = new ConnectionListener(capture);
        try {
            AdminConnectionHook.apply(api, connectionListener, true);
            monitorRegistered = true;
        } catch (RuntimeException e) {
            monitorRegistered = false; // recordings then carry connection_state=UNKNOWN (plan H1)
        }
        capture.connection(monitorRegistered ? Frames.CONN_MONITOR_ACTIVE : Frames.CONN_MONITOR_UNAVAILABLE);
        forwarder = new Forwarder(capture, new HelloInfo(alias, info, monitorRegistered));
        forwarder.start();
    }

    @Override
    public void stop() {
        if (!owner) {
            return;
        }
        if (monitorRegistered) {
            try {
                AdminConnectionHook.apply(api, connectionListener, false);
            } catch (RuntimeException e) {
                // unloading anyway
            }
            monitorRegistered = false;
        }
        forwarder.shutdown(Frames.STOP_JOIN_TIMEOUT_MS);
        owner = false;
        ACTIVE.set(false);
    }

    @Override
    public void onDepth(boolean isBid, int price, int size) {
        if (owner) {
            capture.depth(isBid, price, size);
        }
    }

    @Override
    public void onTrade(double price, int size, TradeInfo tradeInfo) {
        if (owner) {
            capture.trade(price, size, tradeInfo.isBidAggressor, tradeInfo.isOtc, tradeInfo.isExecutionStart,
                    tradeInfo.isExecutionEnd);
        }
    }

    @Override
    public void onTimestamp(long t) {
        if (owner) {
            capture.timestamp(t);
        }
    }

    @Override
    public void onRealtimeStart() {
        if (owner) {
            capture.realtimeStart();
        }
    }

    @Override
    public void onSnapshotEnd() {
        if (owner) {
            capture.snapshotEnd();
        }
    }
}

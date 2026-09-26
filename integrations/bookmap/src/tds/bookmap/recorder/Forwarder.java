package tds.bookmap.recorder;

import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * The only thread that touches the pipe. It opens {@link Frames#PIPE_PATH} for writing only (BMREC-05: nothing is
 * ever read from it), drains the capture queue, emits the timer heartbeat even when the market is quiet, and
 * reconnects with capped exponential backoff. It is a daemon thread and exits within
 * {@link Frames#STOP_JOIN_TIMEOUT_MS} of {@link #shutdown} (BMREC-17).
 */
final class Forwarder implements Runnable {
    private static final int BATCH = 1024;
    private static final int BUF_BYTES = 1 << 20;

    private final Capture capture;
    private final HelloInfo hello;
    private final byte[] buf = new byte[BUF_BYTES];
    private int pos;

    private volatile boolean running = true;
    private Thread thread;
    private FileOutputStream out;
    private long sessionSeq;
    private long framesSent;
    private long reconnects;
    private long lastHeartbeatMs;
    private long lastHeartbeatDropped;

    Forwarder(Capture capture, HelloInfo hello) {
        this.capture = capture;
        this.hello = hello;
    }

    void start() {
        Thread t = new Thread(this, "tds-h1-recorder-forwarder");
        t.setDaemon(true);
        thread = t;
        t.start();
    }

    /** Bounded: returns after at most {@code timeoutMs} whether or not the thread has finished. */
    void shutdown(long timeoutMs) {
        running = false;
        Thread t = thread;
        if (t != null) {
            t.interrupt();
            try {
                t.join(timeoutMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }

    @Override
    public void run() {
        long backoff = Frames.RECONNECT_BACKOFF_INITIAL_MS;
        ArrayList<Rec> batch = new ArrayList<>(BATCH);
        ArrayBlockingQueue<Rec> queue = capture.queue();
        while (running) {
            try {
                if (out == null) {
                    if (!openPipe()) {
                        Thread.sleep(backoff);
                        backoff = Math.min(backoff * 2L, Frames.RECONNECT_BACKOFF_CAP_MS);
                        continue;
                    }
                    backoff = Frames.RECONNECT_BACKOFF_INITIAL_MS;
                    sessionSeq = 0L;
                    pos = 0;
                    writeHello();
                    doResync(Frames.CKPT_SESSION_START);
                    lastHeartbeatMs = System.currentTimeMillis();
                    flush();
                }
                Rec r = queue.poll(100L, TimeUnit.MILLISECONDS);
                if (r != null) {
                    batch.add(r);
                    queue.drainTo(batch, BATCH - 1);
                    for (int i = 0; i < batch.size(); i++) {
                        writeCapture(batch.get(i));
                    }
                    batch.clear();
                }
                if (capture.dropPending()) {
                    doResync(Frames.CKPT_AFTER_GAP);
                }
                if (capture.takeSnapshotEndPending()) {
                    doResync(Frames.CKPT_AFTER_SNAPSHOT_END);
                }
                long nowMs = System.currentTimeMillis();
                if (nowMs - lastHeartbeatMs >= Frames.HEARTBEAT_INTERVAL_MS) {
                    lastHeartbeatMs = nowMs;
                    writeHeartbeat();
                }
                flush();
            } catch (InterruptedException e) {
                running = false;
            } catch (IOException e) {
                closePipe();
                reconnects = reconnects + 1L;
            }
        }
        if (out != null) {
            try {
                beginFrame(Frames.T_ADDON_STOP, capture.currentMode(), ++sessionSeq, Capture.nowNs());
                endFrame();
                flush();
            } catch (IOException e) {
                // stopping anyway
            }
        }
        closePipe();
    }

    // ---- pipe

    /** The single allowlisted file-open site (BMREC-03): constant pipe path, append mode, write-only stream. */
    private boolean openPipe() {
        try {
            out = new FileOutputStream(Frames.PIPE_PATH, true);
            return true;
        } catch (IOException e) {
            out = null;
            return false;
        }
    }

    private void closePipe() {
        FileOutputStream o = out;
        out = null;
        pos = 0;
        if (o != null) {
            try {
                o.close();
            } catch (IOException e) {
                // already gone
            }
        }
    }

    private void flush() throws IOException {
        if (pos > 0 && out != null) {
            out.write(buf, 0, pos);
            pos = 0;
        }
    }

    // ---- frames

    private void writeHello() throws IOException {
        beginFrame(Frames.T_HELLO, capture.currentMode(), ++sessionSeq, Capture.nowNs());
        putStr(BuildInfo.addonVersion());
        putStr(BuildInfo.codeSha256());
        putStr(BuildInfo.sourceSha256());
        putInt(Frames.QUEUE_CAPACITY);
        putBool(hello.monitorActive);
        putStr(hello.alias);
        putOStr(hello.symbol);
        putOStr(hello.exchange);
        putOStr(hello.type);
        putOStr(hello.fullName);
        putOStr(hello.requestedSymbol);
        putDouble(hello.pips);
        putDouble(hello.multiplier);
        putDouble(hello.sizeMultiplier);
        putLong(hello.dataDelay);
        putBool(hello.isFullDepth);
        putBool(hello.isCrypto);
        putBool(hello.isApiProtected);
        putBool(hello.isNbboSupported);
        putOStr(hello.recordingTag);
        endFrame();
    }

    private void writeCapture(Rec r) throws IOException {
        beginFrameAt(r.type, r.mode, r.seq, r.recvNs, r.bookmapTimeNs);
        if (r.type == Frames.T_DEPTH) {
            putBool(r.flag);
            putInt(r.price);
            putInt(r.size);
        } else if (r.type == Frames.T_TRADE) {
            putDouble(r.tradePrice);
            putInt(r.size);
            putBool(r.flag);
            putBool(r.otc);
            putBool(r.execStart);
            putBool(r.execEnd);
        } else if (r.type == Frames.T_CONNECTION) {
            putByte(r.state);
        }
        endFrame();
    }

    private void writeHeartbeat() throws IOException {
        long[] c = capture.counters();
        beginFrame(Frames.T_HEARTBEAT, capture.currentMode(), ++sessionSeq, Capture.nowNs());
        putInt(capture.queue().size());
        putInt(Frames.QUEUE_CAPACITY);
        putLong(c[0]);
        putLong(c[1]);
        putLong(framesSent);
        putLong(capture.ignoredAdminMessages());
        putInt((int) Math.min(reconnects, 0x7fffffffL));
        endFrame();
    }

    /**
     * Contract §5: drain + mirror copy under the capture lock, then send the drained records, the GAP (if records
     * were dropped), and a full book checkpoint.
     */
    private void doResync(int reason) throws IOException {
        ArrayList<Rec> drained = new ArrayList<>();
        Capture.Resync s = capture.resync(drained);
        for (int i = 0; i < drained.size(); i++) {
            writeCapture(drained.get(i));
        }
        long now = Capture.nowNs();
        if (s.dropped > 0L) {
            beginFrame(Frames.T_GAP, s.mode, ++sessionSeq, now);
            putByte(Frames.GAP_QUEUE_OVERFLOW);
            putLong(s.dropped);
            endFrame();
        }
        beginFrame(Frames.T_CHECKPOINT_BEGIN, s.mode, ++sessionSeq, now);
        putByte(reason);
        putBool(s.snapshotComplete);
        putInt(s.bidPrices.length);
        putInt(s.askPrices.length);
        putLong(s.captureSeqAt);
        endFrame();
        int levels = 0;
        for (int i = 0; i < s.bidPrices.length; i++) {
            writeLevel(s.mode, now, true, s.bidPrices[i], s.bidSizes[i]);
            levels++;
        }
        for (int i = 0; i < s.askPrices.length; i++) {
            writeLevel(s.mode, now, false, s.askPrices[i], s.askSizes[i]);
            levels++;
        }
        beginFrame(Frames.T_CHECKPOINT_END, s.mode, ++sessionSeq, now);
        putInt(levels);
        endFrame();
    }

    private void writeLevel(int mode, long now, boolean isBid, int price, int size) throws IOException {
        beginFrame(Frames.T_CHECKPOINT_LEVEL, mode, ++sessionSeq, now);
        putBool(isBid);
        putInt(price);
        putInt(size);
        endFrame();
    }

    // ---- encoding (big-endian, contract §1-§2)

    private int frameStart;

    private void beginFrame(int type, int mode, long seq, long recvNs) throws IOException {
        beginFrameAt(type, mode, seq, recvNs, capture.bookmapTimeNs());
    }

    private void beginFrameAt(int type, int mode, long seq, long recvNs, long bookmapNs) throws IOException {
        if (pos > BUF_BYTES - (Frames.FRAME_MAX_BYTES + 4)) {
            flush();
        }
        frameStart = pos;
        putInt(0); // length placeholder
        putShort(Frames.SCHEMA_VERSION);
        putByte(type);
        putByte(mode);
        putLong(seq);
        putLong(recvNs);
        putLong(Capture.nowNs());
        putLong(bookmapNs);
    }

    private void endFrame() {
        int len = pos - frameStart - 4;
        buf[frameStart] = (byte) (len >>> 24);
        buf[frameStart + 1] = (byte) (len >>> 16);
        buf[frameStart + 2] = (byte) (len >>> 8);
        buf[frameStart + 3] = (byte) len;
        framesSent = framesSent + 1L;
    }

    private void putByte(int v) {
        buf[pos++] = (byte) v;
    }

    private void putBool(boolean v) {
        buf[pos++] = (byte) (v ? 1 : 0);
    }

    private void putShort(int v) {
        buf[pos++] = (byte) (v >>> 8);
        buf[pos++] = (byte) v;
    }

    private void putInt(int v) {
        buf[pos++] = (byte) (v >>> 24);
        buf[pos++] = (byte) (v >>> 16);
        buf[pos++] = (byte) (v >>> 8);
        buf[pos++] = (byte) v;
    }

    private void putLong(long v) {
        putInt((int) (v >>> 32));
        putInt((int) v);
    }

    private void putDouble(double v) {
        putLong(Double.doubleToRawLongBits(v));
    }

    private void putStr(String s) {
        byte[] b = s.getBytes(StandardCharsets.UTF_8);
        // An over-long string keeps its true length prefix so the recorder rejects the frame; it is never
        // silently truncated into a valid-looking value. At most STRING_MAX_BYTES + 1 bytes are copied, which
        // keeps the frame inside FRAME_MAX_BYTES.
        int n = Math.min(b.length, Frames.STRING_MAX_BYTES + 1);
        putShort(Math.min(b.length, 0xffff));
        for (int i = 0; i < n; i++) {
            buf[pos++] = b[i];
        }
    }

    private void putOStr(String s) {
        if (s == null) {
            putByte(0);
        } else {
            putByte(1);
            putStr(s);
        }
    }
}

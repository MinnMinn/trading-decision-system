package tds.bookmap.recorder;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;

/**
 * Capture side: runs on Bookmap's callback threads. Never blocks on I/O (BMREC-17): every callback takes the
 * capture lock (held only for in-memory work), assigns the capture sequence number, updates the book mirror and
 * offers the record to the bounded queue without waiting. A failed offer counts a drop; the sequence number it was
 * given is never sent, so the recorder sees the hole (contract §4).
 */
final class Capture {
    private final Object lock = new Object();
    private final ArrayBlockingQueue<Rec> queue;
    private final HashMap<Integer, Integer> bids = new HashMap<>();
    private final HashMap<Integer, Integer> asks = new HashMap<>();

    private long captureSeq;          // guarded by lock
    private long dropped;             // guarded by lock: drops since the last resync
    private long droppedTotal;        // guarded by lock
    private boolean snapshotComplete; // guarded by lock
    private int mode = Frames.MODE_HISTORICAL; // guarded by lock
    private long lastTimeRecordNs = Long.MIN_VALUE; // guarded by lock

    private volatile long bookmapTimeNs = -1L;
    private volatile boolean dropPending;
    private volatile boolean snapshotEndPending;
    private volatile long ignoredAdminMessages;

    Capture(int capacity) {
        this.queue = new ArrayBlockingQueue<>(capacity);
    }

    static long nowNs() {
        Instant t = Instant.now();
        return t.getEpochSecond() * 1_000_000_000L + t.getNano();
    }

    ArrayBlockingQueue<Rec> queue() {
        return queue;
    }

    // ---- callbacks (Bookmap threads)

    void depth(boolean isBid, int price, int size) {
        long now = nowNs();
        synchronized (lock) {
            HashMap<Integer, Integer> side = isBid ? bids : asks;
            if (size == 0) {
                side.remove(price);
            } else {
                side.put(price, size);
            }
            Rec r = newRec(Frames.T_DEPTH, now);
            r.flag = isBid;
            r.price = price;
            r.size = size;
            enqueueLocked(r);
        }
    }

    void trade(double price, int size, boolean bidAggressor, boolean otc, boolean execStart, boolean execEnd) {
        long now = nowNs();
        synchronized (lock) {
            Rec r = newRec(Frames.T_TRADE, now);
            r.tradePrice = price;
            r.size = size;
            r.flag = bidAggressor;
            r.otc = otc;
            r.execStart = execStart;
            r.execEnd = execEnd;
            enqueueLocked(r);
        }
    }

    void timestamp(long t) {
        bookmapTimeNs = t;
        synchronized (lock) {
            if (lastTimeRecordNs == Long.MIN_VALUE || t - lastTimeRecordNs >= Frames.TIME_RECORD_MIN_INTERVAL_NS) {
                lastTimeRecordNs = t;
                enqueueLocked(newRec(Frames.T_TIME, nowNs()));
            }
        }
    }

    void realtimeStart() {
        long now = nowNs();
        synchronized (lock) {
            mode = Frames.MODE_LIVE;
            enqueueLocked(newRec(Frames.T_MODE, now));
        }
    }

    void snapshotEnd() {
        long now = nowNs();
        synchronized (lock) {
            snapshotComplete = true;
            enqueueLocked(newRec(Frames.T_SNAPSHOT_END, now));
        }
        snapshotEndPending = true;
    }

    void connection(int state) {
        long now = nowNs();
        synchronized (lock) {
            Rec r = newRec(Frames.T_CONNECTION, now);
            r.state = state;
            enqueueLocked(r);
        }
    }

    /** onSystemTextMessage / onUserMessage: counted, never described (BMREC-06). */
    void ignoredAdminMessage() {
        synchronized (lock) {
            ignoredAdminMessages = ignoredAdminMessages + 1;
        }
    }

    private Rec newRec(int type, long now) {
        Rec r = new Rec();
        r.type = type;
        r.recvNs = now;
        r.bookmapTimeNs = bookmapTimeNs;
        r.mode = mode;
        return r;
    }

    private void enqueueLocked(Rec r) {
        captureSeq = captureSeq + 1;
        r.seq = captureSeq;
        if (!queue.offer(r)) {
            dropped = dropped + 1;
            droppedTotal = droppedTotal + 1;
            dropPending = true;
        }
    }

    // ---- forwarder side

    boolean dropPending() {
        return dropPending;
    }

    boolean takeSnapshotEndPending() {
        if (snapshotEndPending) {
            snapshotEndPending = false;
            return true;
        }
        return false;
    }

    long bookmapTimeNs() {
        return bookmapTimeNs;
    }

    long ignoredAdminMessages() {
        return ignoredAdminMessages;
    }

    int currentMode() {
        synchronized (lock) {
            return mode;
        }
    }

    long[] counters() {
        synchronized (lock) {
            return new long[] {droppedTotal, captureSeq};
        }
    }

    /**
     * Under the capture lock: drain every queued record into {@code drained}, then copy the book mirror. Records
     * captured after this returns carry sequence numbers greater than {@link Resync#captureSeqAt}.
     */
    Resync resync(ArrayList<Rec> drained) {
        synchronized (lock) {
            queue.drainTo(drained);
            Resync s = new Resync();
            s.dropped = dropped;
            dropped = 0;
            dropPending = false;
            s.captureSeqAt = captureSeq;
            s.snapshotComplete = snapshotComplete;
            s.mode = mode;
            s.bidPrices = new int[bids.size()];
            s.bidSizes = new int[bids.size()];
            copySide(bids, s.bidPrices, s.bidSizes);
            s.askPrices = new int[asks.size()];
            s.askSizes = new int[asks.size()];
            copySide(asks, s.askPrices, s.askSizes);
            return s;
        }
    }

    private static void copySide(HashMap<Integer, Integer> side, int[] prices, int[] sizes) {
        int i = 0;
        Iterator<Map.Entry<Integer, Integer>> it = side.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<Integer, Integer> e = it.next();
            prices[i] = e.getKey().intValue();
            sizes[i] = e.getValue().intValue();
            i++;
        }
    }

    static final class Resync {
        long dropped;
        long captureSeqAt;
        boolean snapshotComplete;
        int mode;
        int[] bidPrices;
        int[] bidSizes;
        int[] askPrices;
        int[] askSizes;
    }
}

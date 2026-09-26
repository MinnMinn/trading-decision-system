package tds.bookmap.recorder;

/** One captured callback, queued for the forwarder. Plain mutable holder; created on the callback thread only. */
final class Rec {
    int type;
    long seq;
    long recvNs;
    long bookmapTimeNs;
    int mode;
    boolean flag;       // DEPTH: isBid; TRADE: isBidAggressor
    int price;          // DEPTH: price level
    int size;           // DEPTH/TRADE: size
    double tradePrice;  // TRADE: (possibly fractional) price level
    boolean otc;
    boolean execStart;
    boolean execEnd;
    int state;          // CONNECTION: state enum
}

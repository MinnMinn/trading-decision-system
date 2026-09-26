package tds.bookmap.recorder;

import velox.api.layer1.data.InstrumentInfo;

/** InstrumentInfo facts copied once at initialize (field reads only, BMREC-01). */
final class HelloInfo {
    final String alias;
    final String symbol;
    final String exchange;
    final String type;
    final String fullName;
    final String requestedSymbol;
    final double pips;
    final double multiplier;
    final double sizeMultiplier;
    final long dataDelay;
    final boolean isFullDepth;
    final boolean isCrypto;
    final boolean isApiProtected;
    final boolean isNbboSupported;
    final String recordingTag;
    final boolean monitorActive;

    HelloInfo(String alias, InstrumentInfo info, boolean monitorActive) {
        this.alias = alias == null ? "" : alias;
        this.symbol = info.symbol;
        this.exchange = info.exchange;
        this.type = info.type;
        this.fullName = info.fullName;
        this.requestedSymbol = info.requestedSymbol;
        this.pips = info.pips;
        this.multiplier = info.multiplier;
        this.sizeMultiplier = info.sizeMultiplier;
        this.dataDelay = info.dataDelay;
        this.isFullDepth = info.isFullDepth;
        this.isCrypto = info.isCrypto;
        this.isApiProtected = info.isApiProtected;
        this.isNbboSupported = info.isNbboSupported;
        this.recordingTag = info.recordingTag;
        this.monitorActive = monitorActive;
    }
}

#!/usr/bin/env bash
# Retrieves a named secret from macOS Keychain -- the platform-secure-storage
# path required by docs/security-equivalent rules (never plaintext on disk).
# Usage: get-secret.sh <secret-name> [keychain-account]
#   e.g. get-secret.sh trading-system-binance-testnet-api-key                      (account binance-testnet)
#        get-secret.sh trading-system-binance-futures-testnet-api-key binance-futures-testnet
#
# Caller must capture the output into a variable and never echo/print it.
set -euo pipefail
NAME="${1:?Usage: get-secret.sh <secret-name> [keychain-account]}"
ACCOUNT="${2:-binance-testnet}"
security find-generic-password -a "$ACCOUNT" -s "$NAME" -w

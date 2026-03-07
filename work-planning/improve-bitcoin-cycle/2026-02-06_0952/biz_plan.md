# Fix Bitcoin Cycle Chart: Optimized Fallback

## User Request
- "바이낸스 한번 트라이하고 안되면 바로 다음 차선책을 사용해." (Try Binance once, if fail, immediately fallback).

## Solution
- **Reduced Timeout**: Decreased fetch timeout from 3000ms to **1500ms** for each provider. This ensures faster failover.
- **Cache Busting**: Added timestamp query param `?_=${Date.now()}` to all fetch URLs to bypass browser caching of failed/stale responses.

## Plan
- [x] Update `fetchLivePrice` timeouts.
- [x] Add cache busting query params.

## Status
- **Complete**. The system now aggressively switches to backup providers (Coinbase/CoinGecko) if Binance hangs or fails, ensuring the live price is loaded as quickly as possible.

# Migrating from `trading_simulator_with_algorithmic_traders.py` to `trading_simulator/`

This adds a proper `trading_simulator/` package next to the original
single-file script. The original file is left untouched -- nothing was
deleted -- so you can diff, compare, and delete it yourself once you're
happy with the migration.

## Why this exists

The single script had grown to 4,556 lines and ~25 classes in one file, with
no tests, no packaging, and several real bugs (see below). The README's own
Quick Start examples (`from trading_simulator import MomentumTrader`) never
actually worked, because no `trading_simulator` module existed anywhere in
the repo -- only `trading_simulator_with_algorithmic_traders.py`. This
package **is** that module now; the README's existing code samples should
work close to verbatim against it.

## What changed in behavior (not just structure)

1. **Self-trade prevention no longer corrupts order priority.** The
   original skipped a same-owner resting order by `deque.rotate(-1)`, which
   permanently moved that order to the back of the price-time-priority
   queue -- so every self-trade skip silently stole priority from someone
   else's order. Fixed in `core/matching_engine.py`; covered by
   `tests/test_matching_engine.py::test_self_trade_prevention_preserves_priority`.

2. **FOK (fill-or-kill) checks exclude the taker's own resting liquidity.**
   Previously a FOK order could count its own resting quotes as "available
   depth," pass the pre-check, then fail to actually fill against them
   (self-trade prevention blocks that) -- an accept/execute mismatch. Fixed;
   covered by `test_matching_engine.py::test_fok_excludes_own_liquidity`.

3. **The market maker's quotes now go through the same `match_order()` path
   as every other order**, instead of calling `order_book.add_order()`
   directly. Previously MM quotes silently skipped pre-trade risk checks,
   price-band protection, halted-symbol checks, and audit logging. One
   behavioral consequence: an MM quote that crosses the book now fills
   immediately (as taker) instead of only ever resting.

4. **The market maker's drawdown kill-switch was measuring the wrong
   thing** and was caught by actually running a backtest, not just reading
   the code: it computed `equity = inventory * mid` and drawdown as a
   fraction of *peak equity*, but `inventory` is a small signed number that
   crosses zero constantly, so "peak equity" was often tiny and the
   drawdown fraction routinely blew up to 90%+ on ordinary inventory swings
   -- the kill-switch fired almost immediately and stayed latched. It now
   tracks realized cash flow + mark-to-market inventory as a real P&L
   figure, and measures drawdown against a configurable `capital_base`
   (default $100,000) instead of its own noisy peak.

5. **`OrderBook` now has its own lock**, not just `MatchingEngine`. Any
   strategy or market maker reading `matching_engine.order_book` directly
   (a pattern the README itself documents for custom traders) was
   unsynchronized in live/threaded mode.

6. **The sentiment trader remembers headlines it has already traded on.**
   The original re-fetched the same ~5 latest headlines every poll interval
   and re-traded every one of them every time, with no memory -- it would
   keep re-buying/re-selling on stale news indefinitely. It now keeps a
   bounded LRU cache of seen headlines and skips ones it's already acted on.

7. **Momentum/EMA/Swing traders can size orders as a fraction of account
   equity** instead of a hardcoded 100 shares (pass `portfolio=...` and
   optionally `risk_fraction=...`; omit both to keep the old fixed-100
   behavior).

8. **The FIX adapter fixes three concrete bugs**: one `FixParser` was
   shared across all TCP connections (corrupts message framing if two
   clients connect around the same time); the accept loop handled exactly
   one message from exactly one client then closed (a message split across
   TCP packets was silently dropped); and outgoing messages appended a fake
   hardcoded checksum (`b'000'`) that `simplefix`'s own `encode()` already
   computes correctly. It's still a simplified educational adapter with no
   Logon/Heartbeat/sequence-number session layer -- that's now stated
   explicitly rather than implied by "industry-standard FIX 4.2 protocol
   integration."

9. **Per-instrument tick size / lot size / trading hours** moved from
   module-level global dicts (shared, mutable, process-wide) to an
   `InstrumentRegistry` you can instantiate per engine -- so parallel
   backtests, Optuna trials, and tests no longer leak configuration into
   each other.

10. **Custom strategy loading now validates the class** before
    instantiating it (`strategies.registry.load_custom_trader`). A
    typo'd `--custom-trader` spec now fails with a clear message at load
    time instead of a confusing `AttributeError` deep in the trading loop.

## What's new

- `trading_simulator.execution_algos`: TWAP/VWAP parent-order slicing
  (`twap_schedule`, `vwap_schedule`) for splitting large orders into smaller
  clips -- a real institutional execution pattern that wasn't present at
  all before.
- A pytest suite (`tests/`) covering the matching engine, portfolio,
  risk manager, and strategies -- there were no automated tests before.
- `requirements.txt` / `requirements-full.txt` / `requirements-dev.txt`,
  `pyproject.toml`, `LICENSE` (MIT), `CONTRIBUTING.md`, `.env.example`, and
  `examples/strats.py` -- all referenced by the README already, none of
  them existed in the repository.
- A GitHub Actions CI workflow (`.github/workflows/ci.yml`) running the
  test suite on Python 3.10-3.12.

## How to run it

```bash
pip install -r requirements-dev.txt   # or requirements-full.txt for every optional integration
pip install -e .
pytest                                 # run the test suite
python -m trading_simulator.cli.main   # guided CLI (same UX as before)
python -m trading_simulator.cli.main --mode backtest --symbol AAPL --enable-traders --export-report
```

Or, once installed, the console script:

```bash
trading-simulator --mode backtest --symbol AAPL --enable-traders
```

## What I did not do (be aware before you delete the old script)

- I did not rewrite the 45KB `README.md` end-to-end. Its existing "Quick
  Start" / "Trading Strategies" code samples should now work close to
  verbatim (they import from `trading_simulator`, which now exists), but
  the installation section still points at `python
  trading_simulator_with_algorithmic_traders.py` as the entry point --
  update that to `python -m trading_simulator.cli.main` (or the
  `trading-simulator` console script) when you're ready to retire the old
  script.
- I did not build a certified FIX session layer (Logon/Heartbeat/sequence
  numbers) -- see point 8 above.
- I did not change the core matching algorithm's asymptotic behavior
  (finding a price level with a non-self-owner is still an O(depth) scan);
  documented as a known limitation in `core/matching_engine.py` rather than
  silently left unmentioned.

## Testing pass: bugs found while actually exercising the system

The refactor above shipped with 9 tests covering the headline bug fixes. A
follow-up pass wrote 91 tests exercising every module end to end (matching
engine, order book, portfolio, risk manager, strategies, market maker,
router, snapshots/replay, auctions, socket-level order-CLI, EventBus/
Redis/Kafka guards, optional-dependency graceful degradation, and the CLI
itself) and, in the process of actually running the CLI rather than just
reading it, found and fixed several real bugs:

1. **The entire "Event Streaming" feature (`EventBus`, `make_redis_publisher`,
   `make_kafka_publisher`) had been silently dropped** during the original
   rewrite -- the README advertised it, but there were zero references to
   `EventBus` anywhere in the delivered package. Re-implemented in
   `trading_simulator/streaming/`, re-exported from the top-level package,
   and covered by `tests/test_streaming.py`.

2. **Every single backtest/replay/live run crashed** with
   `AttributeError: 'Namespace' object has no attribute 'mm_gamma'`. The
   market maker is constructed unconditionally in all three modes
   (`_build_market_maker` reads `args.mm_gamma`, `args.mm_k`, and eleven
   other `mm_*` attributes), but `cli/args.py` never registered any
   `--mm-*` flags with argparse -- so the Namespace never had them, even
   though the guided CLI's `prompts.py` already assumed they existed. This
   was the single most severe bug found this pass: the primary "run a
   backtest" path was completely non-functional. Fixed by adding all
   thirteen `--mm-*` flags (plus a new `--mm-capital-base`, wired through to
   `MarketMaker`'s `capital_base` parameter, which previously had no CLI
   flag at all) to `cli/args.py` with defaults matching `MarketMaker`'s own
   constructor defaults. Covered by `tests/test_cli.py`'s end-to-end
   backtest/replay tests, which exercise `_build_market_maker` directly.

3. **`OrderCliServer.start()` had a start/connect race.** `start()` spawned
   the accept-loop thread and returned immediately, before the socket was
   guaranteed to be bound and listening -- a caller that tried to connect
   right after `start()` returned could hit "connection refused"
   intermittently. `start()` now blocks (with a timeout) on a
   `threading.Event` that the server thread sets only after `bind()` +
   `listen()` succeed. `start(port=0)` also now exposes the OS-assigned
   ephemeral port via `.port` after `start()` returns, instead of only
   supporting a fixed pre-chosen port.

4. **`--order-cli-port 0` (ephemeral port) logged the wrong port.**
   `_run_live_mode` logged `args.order_cli_port` (still `0`, the requested
   value) instead of `order_cli.port` (the real OS-assigned port set by
   fix #3 above) -- so a user requesting an ephemeral port had no way to
   discover which port to actually connect to from the log output. Found by
   manually running live mode with `--order-cli-port 0`. Fixed by extracting
   a `_start_order_cli()` helper that logs `order_cli.port`; covered by
   `tests/test_cli.py::test_start_order_cli_logs_actual_bound_port_not_requested_zero`.

5. **`DbLogger` was bound to plain `None` when SQLAlchemy wasn't
   installed**, so `DbLogger(uri)` failed with a confusing
   `TypeError: 'NoneType' object is not callable` instead of an actionable
   message -- inconsistent with `FixApplication` and `SentimentAnalysisTrader`,
   which both raise a clear `RuntimeError` naming the missing package. Fixed
   by defining a stub `DbLogger` class in the `except ImportError` branch
   that raises `RuntimeError` on construction. Covered by
   `tests/test_optional_deps.py`.

6. **Auction orders could vanish silently if there was no cross at uncross
   time.** `uncross_auction()`'s no-cross branch discarded pooled
   auction-only orders with no log line at all. Now logs a warning naming
   exactly which order IDs were discarded. Covered by
   `tests/test_auctions.py::test_auction_uncross_no_cross_discards_pool_with_warning`.

7. **The guided CLI's Ctrl+C handling had a gap.** `run_guided_cli()`
   wrapped the mode-specific sub-flows (`_backtest_flow`, `_replay_flow`,
   etc.) in `try/except KeyboardInterrupt`, but not the very first prompt
   ("Enter choice [1-5]") -- so hitting Ctrl+C at the mode-selection prompt
   crashed with a raw traceback instead of the clean "Cancelled." message
   the rest of the flow gives. Fixed by widening the `try` block to cover
   the initial prompt too. Covered by
   `tests/test_cli.py::test_guided_cli_keyboard_interrupt_returns_none`.

8. **Raw tracebacks on expected, actionable failures.** Running a backtest
   without a market data provider installed (or with a bad custom-trader
   spec, etc.) printed a full Python traceback. `cli/main.py`'s `main()` now
   catches `RuntimeError`/`ValueError`/`FileNotFoundError` and prints one
   clean line plus `exit(1)` instead -- pass the new `--debug` flag to get
   the full traceback back when you're actually debugging the library.
   `history.py`'s error message was also improved to distinguish "no
   provider installed" (with a `pip install` hint and a `--mode demo`
   suggestion) from "providers installed but no data returned" (suggests a
   bad symbol/date range/network issue).

9. **`python -m trading_simulator.cli.main` emitted a `RuntimeWarning`**
   about a module already being imported. Added `trading_simulator/__main__.py`
   so `python -m trading_simulator` is the clean, documented entry point.

10. **`OrderBook.cancel_order`'s "not found" case logged at `WARNING`**,
    which is noisy in normal operation -- cancelling an order that just got
    filled a moment earlier is a benign, expected race, not a warning-worthy
    event. Downgraded to `INFO`.

None of the above were caught by reading the code in isolation -- all ten
were found by writing tests that actually import and exercise every module,
and by manually running the CLI through every mode (demo, backtest, replay,
live, guided, advanced, `--debug`, custom traders, order-CLI, liquidity
injection) rather than assuming the ported code worked because it compiled.

**Test count: 9 -> 91.** New test files: `test_streaming.py`,
`test_order_cli.py`, `test_auctions.py`, `test_snapshots_and_replay.py`,
`test_router.py`, `test_cli.py`, `test_optional_deps.py`.

## FIX engine: from a message-format demo to a real session layer

The original FIX adapter (both in the single-file script and the first cut
of the packaged `connectivity/fix_app.py`) had zero session semantics: one
shared `simplefix.parser.FixParser()` reused across every connection
(corrupting state if two clients connected), a connection that handled
exactly one message then closed, and a literal `b"1"`/`b"0"` ack byte
instead of a real FIX message. No Logon requirement, no Heartbeat, no
sequence numbers, no resend logic -- calling it "simplified" was accurate,
not self-deprecating.

This session replaced that with a genuine, if still honestly-scoped, FIX
engine:

- **`connectivity/fix_session.py`** (new): a pure, dependency-free
  `FixSessionState` state machine implementing Logon negotiation (including
  `ResetSeqNumFlag`), MsgSeqNum tracking in both directions, sequence-gap
  detection that issues a real `ResendRequest`, `ResendRequest` handling
  that replays *actual* previously-sent messages with `PossDupFlag=Y` (not
  just a gap-fill stub), `SequenceReset` handling, Heartbeat/`TestRequest`
  timers (`due_for_heartbeat`/`due_for_test_request`/`due_for_disconnect`),
  and Logout. Deliberately decoupled from `simplefix`/sockets so it's fully
  unit-testable: `tests/test_fix_session.py` (11 tests, zero external
  dependencies) proves Logon handshakes, gap-triggered resend + replay,
  stale-duplicate rejection, TestRequest/Heartbeat round trips, and Logout
  on both sides.
- **`connectivity/fix_app.py`** (rewritten): `FixApplication` (acceptor) now
  creates one `FixSessionState` per connection, refuses business messages
  before Logon (`FixSessionError` -> protocol-violation Logout), and turns
  order flow into real `ExecutionReport` (35=8) on New/PartialFill/Fill/
  Canceled and `Reject` (35=3) on malformed `NewOrderSingle`/
  `OrderCancelRequest`, routed back to the right connection via a
  `ClOrdID -> connection` table populated on submission and consulted from
  a callback subscribed once to `matching_engine.subscribe_trades()`. A
  per-connection watchdog thread sends unsolicited Heartbeats and answers
  dead connections per the timers above.
- **`FixClient`** (new): the initiator/client counterpart that was simply
  missing before -- connects, logs on (blocking until acknowledged or a
  timeout), sends `NewOrderSingle`/`OrderCancelRequest` with correctly
  sequenced headers, collects `ExecutionReport`s, and logs out cleanly. The
  acceptor had nothing that could talk to it correctly end to end without
  this.
- New CLI flags `--fix-sender-comp-id`, `--fix-target-comp-id`,
  `--fix-heartbeat-interval` (plus a guided-CLI prompt) so the session
  identity and timing are actually configurable instead of hardcoded.

**Honest limits of what could be verified here:** this sandbox has no
network access to `pip install simplefix`, so while `FixSessionState`'s
logic is proven by running its test suite, the `simplefix`-dependent wire
encode/decode in `FixApplication`/`FixClient` could only be written,
syntax-checked, and carefully reasoned through against the session-layer
tests -- not executed against a live socket. If you have `simplefix`
installed locally, running a real two-process Logon -> NewOrderSingle ->
ExecutionReport -> Logout exchange (see the README's FIX Protocol Engine
section for the exact snippet) is the next verification step. Remaining
scope limits even so: no encryption, no FIX 5.0/FIXT split-session profile,
no message store surviving a process restart, no out-of-order message
buffering.

**Test count: 91 -> 109.** New test files: `test_fix_session.py` (11
tests), `test_fix_app_logic.py` (7 tests); `test_optional_deps.py` gained a
`FixClient` clean-error test.

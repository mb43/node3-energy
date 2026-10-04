#!/usr/bin/env python3
"""
deploy_async_backtest.py
Root cause: _run_backtest() runs synchronously in the Flask request thread.
When cache is stale, /api/backtest blocks the server for 2-5 minutes, making
every other endpoint (fleet, prices, history) queue behind it — the dashboard
appears hung.

Fix: background thread + immediate 202 response with {status:"running"}.
Client polls every 30s until {status:"complete"} and renders.

Run on Pi: python3 deploy_async_backtest.py
"""
import os

BASE = '/home/pi/node3'
SRV  = os.path.join(BASE, 'server.py')
DASH = os.path.join(BASE, 'dashboard.html')

def patch(path, old, new, label):
    with open(path) as f:
        src = f.read()
    if old not in src:
        print(f'✗ NOT FOUND: {label}')
        return False
    c = src.count(old)
    if c > 1:
        print(f'✗ AMBIGUOUS ({c} matches): {label}')
        return False
    with open(path, 'w') as f:
        f.write(src.replace(old, new, 1))
    print(f'✓ {label}')
    return True

# ──────────────────────────────────────────────────────────────────
# SERVER PATCH 1: Add background-thread state tracking after imports
# ──────────────────────────────────────────────────────────────────
patch(SRV,
    '# Called by /api/backtest; result cached 24h in backtest_cache.json.',
    '''# Called by /api/backtest; result cached 24h in backtest_cache.json.
# Background threading state — tracks in-flight LP backtest jobs so the
# request handler can return immediately without blocking Flask.
_bt_lock    = threading.Lock()
_bt_running = {}   # key: 'consumer' | 'founder', value: True while running''',
    'SERVER PATCH 1: Add background-thread state vars')

# ──────────────────────────────────────────────────────────────────
# SERVER PATCH 2: Replace synchronous api_backtest handler with
#                 async background-thread version
# ──────────────────────────────────────────────────────────────────
OLD_API = '''def api_backtest():
    """12-month backtest. ?mode=founder uses baseload_kw; default uses baseload_kw_consumer."""
    founder    = request.args.get('mode', '').lower() == 'founder'
    cache_file = "backtest_cache_founder.json" if founder else "backtest_cache.json"
    cache_path = os.path.join(BASE_DIR, cache_file)
    force      = request.args.get('force', '').lower() in ('1', 'true', 'yes')

    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            cached_at = cached.get('_cached_at', 0)
            age_h = (time.time() - cached_at) / 3600
            if age_h < 24:
                print(f'[BACKTEST] Cache hit ({age_h:.1f}h old)')
                out = dict(cached['data'])
                # Surface generation time in the payload itself — not just the
                # server-side cache wrapper — so the dashboard can show the user
                # exactly how fresh these numbers are instead of presenting them
                # as unconditionally live. See stale-data watchdog, 19 Aug 2026.
                out['_generated_at'] = datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat()
                return jsonify(out)
        except Exception as e:
            print(f'[BACKTEST] Cache read error: {e}')

    try:
        data = _run_backtest(founder=founder)
        now_ts = time.time()
        try:
            with open(cache_path, 'w') as f:
                json.dump({'_cached_at': now_ts, 'data': data}, f)
        except Exception as e:
            print(f'[BACKTEST] Cache write error: {e}')
        data['_generated_at'] = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        return jsonify(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500'''

NEW_API = '''def api_backtest():
    """12-month LP backtest. ?mode=founder uses baseload_kw; default uses baseload_kw_consumer=0.
    Returns cached result immediately if < 24h old.
    If cache is stale/missing: starts a background thread and returns {status:'running'} at once
    so Flask is never blocked and the dashboard stays responsive while the LP runs.
    Client polls every 30s; when the thread finishes writing the cache the next poll
    returns the full result.
    """
    founder    = request.args.get('mode', '').lower() == 'founder'
    mode_key   = 'founder' if founder else 'consumer'
    cache_file = "backtest_cache_founder.json" if founder else "backtest_cache.json"
    cache_path = os.path.join(BASE_DIR, cache_file)
    force      = request.args.get('force', '').lower() in ('1', 'true', 'yes')

    # ── Serve fresh cache immediately (most common path) ──────────────────────
    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            cached_at = cached.get('_cached_at', 0)
            age_h = (time.time() - cached_at) / 3600
            if age_h < 24:
                print(f'[BACKTEST] Cache hit ({age_h:.1f}h old, mode={mode_key})')
                out = dict(cached['data'])
                out['_generated_at'] = datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat()
                return jsonify(out)
        except Exception as e:
            print(f'[BACKTEST] Cache read error: {e}')

    # ── Cache stale/missing: run in background, return 202 immediately ────────
    def _bg_run(founder_flag, key, cpath):
        print(f'[BACKTEST] Background thread starting (mode={key})…')
        try:
            data   = _run_backtest(founder=founder_flag)
            now_ts = time.time()
            with open(cpath, 'w') as f:
                json.dump({'_cached_at': now_ts, 'data': data}, f)
            print(f'[BACKTEST] Background thread done (mode={key}), cache written.')
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f'[BACKTEST] Background thread error (mode={key}): {exc}')
        finally:
            with _bt_lock:
                _bt_running.pop(key, None)

    with _bt_lock:
        already = _bt_running.get(mode_key, False)
        if not already:
            _bt_running[mode_key] = True
            t = threading.Thread(target=_bg_run, args=(founder, mode_key, cache_path), daemon=True)
            t.start()
            print(f'[BACKTEST] Spawned background thread (mode={mode_key})')

    return jsonify({
        'status':  'running',
        'mode':    mode_key,
        'message': 'LP backtest running in background (2–4 min on Pi) — poll again shortly',
    }), 202'''

patch(SRV, OLD_API, NEW_API, 'SERVER PATCH 2: Make api_backtest async (background thread)')

# ──────────────────────────────────────────────────────────────────
# DASHBOARD PATCH: loadHistoricalData() handles {status:"running"}
# Polls every 30s until a real result arrives
# ──────────────────────────────────────────────────────────────────
OLD_HIST = '''    const resp = await fetch(url, { signal: AbortSignal.timeout(180000) }); // 3 min max
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.error || `Server error HTTP ${resp.status}`);
    }

    updateHistProg(0, 90, 'RENDERING RESULTS…');
    const results = await resp.json();
    if (results.error) throw new Error(results.error);

    histResultsCache = results;
    renderHistoricalResults(results);
    updateSecondaryTabs();

    prog.style.display = 'none';
    res.style.display  = 'block';
    btn.textContent    = '↻ REFRESH HISTORICAL DATA';
    btn.disabled       = false;
    btn.onclick        = () => loadHistoricalData(true);  // manual refresh = force re-run

    res.scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch(e) {
    prog.style.display = 'none';
    err.style.display  = 'block';
    err.textContent    = '⚠ ' + e.message;
    btn.textContent    = '⚡ LOAD 12 MONTHS OF REAL DATA';
    btn.disabled       = false;
    console.error('[HIST]', e);'''

NEW_HIST = '''    const resp = await fetch(url, { signal: AbortSignal.timeout(15000) }); // 15s — returns fast now (async server)
    const results = await resp.json().catch(() => ({}));

    // ── Async backtest: server spawned background thread, poll until done ──
    if (resp.status === 202 || results.status === 'running') {
      const pollMsg = results.message || 'LP backtest running on server…';
      updateHistProg(0, 10, '⏳ ' + pollMsg);
      btn.textContent = 'BACKTEST RUNNING — auto-polling…';

      // Poll every 30s (backtest takes 2-4 min on Pi)
      await new Promise((resolve, reject) => {
        let attempt = 0;
        const MAX_ATTEMPTS = 12; // 12 × 30s = 6 min max wait
        const pollTimer = setInterval(async () => {
          attempt++;
          updateHistProg(0, Math.min(10 + attempt * 7, 80), `⏳ Backtest running… poll ${attempt}/${MAX_ATTEMPTS}`);
          try {
            const pollResp = await fetch(url.replace(/[?&]force[=\w]*/g, ''), { signal: AbortSignal.timeout(15000) });
            const pollData = await pollResp.json().catch(() => ({}));
            if (pollResp.status !== 202 && pollData.status !== 'running' && !pollData.error) {
              clearInterval(pollTimer);
              resolve(pollData);
            } else if (pollData.error) {
              clearInterval(pollTimer);
              reject(new Error(pollData.error));
            } else if (attempt >= MAX_ATTEMPTS) {
              clearInterval(pollTimer);
              reject(new Error('Backtest timed out after 6 min — check Pi CPU / logs'));
            }
          } catch(pe) {
            if (attempt >= MAX_ATTEMPTS) { clearInterval(pollTimer); reject(pe); }
          }
        }, 30000);
      }).then(pollData => {
        // Arrived here with real data — fall through to render
        histResultsCache = pollData;
        renderHistoricalResults(pollData);
        updateSecondaryTabs();
        prog.style.display = 'none';
        res.style.display  = 'block';
        btn.textContent    = '↻ REFRESH HISTORICAL DATA';
        btn.disabled       = false;
        btn.onclick        = () => loadHistoricalData(true);
        res.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      return; // polling branch handled above
    }

    if (results.error) throw new Error(results.error);
    if (!resp.ok) throw new Error(`Server error HTTP ${resp.status}`);

    updateHistProg(0, 90, 'RENDERING RESULTS…');
    histResultsCache = results;
    renderHistoricalResults(results);
    updateSecondaryTabs();

    prog.style.display = 'none';
    res.style.display  = 'block';
    btn.textContent    = '↻ REFRESH HISTORICAL DATA';
    btn.disabled       = false;
    btn.onclick        = () => loadHistoricalData(true);  // manual refresh = force re-run

    res.scrollIntoView({ behavior: 'smooth', block: 'start' });

  } catch(e) {
    prog.style.display = 'none';
    err.style.display  = 'block';
    err.textContent    = '⚠ ' + e.message;
    btn.textContent    = '⚡ LOAD 12 MONTHS OF REAL DATA';
    btn.disabled       = false;
    console.error('[HIST]', e);'''

patch(DASH, OLD_HIST, NEW_HIST, 'DASHBOARD PATCH: loadHistoricalData polls async backtest')

print('\n✅ Done. On Pi:')
print('  docker compose restart node3')
print('\nBehaviour after deploy:')
print('  • If backtest cache is fresh (< 24h): /api/backtest returns instantly as before')
print('  • If cache is stale/missing: returns 202 {status:"running"} immediately,')
print('    spawns background thread, dashboard polls every 30s — no more blocked server')
print('  • All other endpoints (fleet, prices, history) respond instantly regardless')

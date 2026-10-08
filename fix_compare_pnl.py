#!/usr/bin/env python3
"""fix_compare_pnl.py — Add full Dovecote P&L to backtest-compare response.

Currently net_gbp = gross − SC only.
True Dovecote P&L = gross (arbitrage) + subscription revenue − standing charge.

This patch adds to each mode dict:
  subscription_gbp       — subscription_pcm × prorated months for actual days
  dovecote_net_gbp       — gross + subscription - SC  (true bottom line)
  annualised_dovecote_gbp — annualised dovecote_net
  vs_agile_dovecote_gbp  — delta vs agile baseline on dovecote_net (split/optimise)

Also adds subscription_pcm and subscription_annual_gbp to the top-level payload.

Run on Pi: python3 /tmp/fix_compare_pnl.py
"""
from pathlib import Path

SRV = Path('/home/pi/node3/server.py')
text = SRV.read_text('utf-8')

# ── Patch 1: read subscription_pcm in the compare function ───────────────────
# Insert after sc_eon is read (line ~1170)

OLD_SC_READ = (
    '    sc_agile = (float(cfg.get("standing_charge_import_p_day", 62.22)) +\n'
    '                float(cfg.get("standing_charge_export_p_day", 0.0)))\n'
    '    sc_eon   = float(cfg.get("standing_charge_eon_p_day", 62.22))\n'
)
NEW_SC_READ = (
    '    sc_agile       = (float(cfg.get("standing_charge_import_p_day", 62.22)) +\n'
    '                      float(cfg.get("standing_charge_export_p_day", 0.0)))\n'
    '    sc_eon         = float(cfg.get("standing_charge_eon_p_day", 62.22))\n'
    '    subscription_pcm = float(cfg.get("subscription_pcm", 0.0))  # £/month from homeowner\n'
)

if OLD_SC_READ in text:
    text = text.replace(OLD_SC_READ, NEW_SC_READ, 1)
    print('[OK]   server.py: subscription_pcm read in compare function')
elif 'subscription_pcm = float(cfg.get("subscription_pcm"' in text:
    print('[SKIP] server.py: subscription_pcm already read in compare')
else:
    print('[WARN] server.py: sc_agile/sc_eon anchor not found in compare')

# ── Patch 2: add subscription + dovecote_net to per-mode dict ────────────────

OLD_MODE_DICT = (
            '            days = r.get("days", months * 30.5)\n'
            '            # Standing charges differ by tariff\n'
            '            sc_p_day = sc_agile if mode == "agile" else sc_eon\n'
            '            sc_total = sc_p_day * days / 100.0\n'
            '            gross    = r["total"]\n'
            '            net      = round(gross - sc_total, 2)\n'
            '            results[mode] = {\n'
            '                "gross_gbp":            round(gross, 2),\n'
            '                "standing_charge_gbp":  round(sc_total, 2),\n'
            '                "net_gbp":              net,\n'
            '                "annualised_gross_gbp": round(gross * 365 / max(1, days), 2),\n'
            '                "annualised_net_gbp":   round(net   * 365 / max(1, days), 2),\n'
            '                "days":                 round(days, 1),\n'
            '                "avg_buy_p":            r.get("buyThr", 0),\n'
            '                "avg_sell_p":           r.get("sellThr", 0),\n'
            '                "total_charge_kwh":     r.get("totalChargeKwh", 0),\n'
            '                "total_discharge_kwh":  r.get("totalDischargeKwh", 0),\n'
            '            }\n'
)
NEW_MODE_DICT = (
            '            days = r.get("days", months * 30.5)\n'
            '            # Standing charges differ by tariff\n'
            '            sc_p_day      = sc_agile if mode == "agile" else sc_eon\n'
            '            sc_total      = sc_p_day * days / 100.0\n'
            '            gross         = r["total"]\n'
            '            net           = round(gross - sc_total, 2)\n'
            '            # Subscription revenue: prorated to actual days in backtest period\n'
            '            sub_gbp       = round(subscription_pcm * days / 30.4375, 2)\n'
            '            dovecote_net  = round(gross + sub_gbp - sc_total, 2)\n'
            '            results[mode] = {\n'
            '                "gross_gbp":              round(gross, 2),\n'
            '                "standing_charge_gbp":    round(sc_total, 2),\n'
            '                "subscription_gbp":       sub_gbp,\n'
            '                "net_gbp":                net,\n'
            '                "dovecote_net_gbp":       dovecote_net,\n'
            '                "annualised_gross_gbp":   round(gross * 365 / max(1, days), 2),\n'
            '                "annualised_net_gbp":     round(net   * 365 / max(1, days), 2),\n'
            '                "annualised_dovecote_gbp":round(dovecote_net * 365 / max(1, days), 2),\n'
            '                "days":                   round(days, 1),\n'
            '                "avg_buy_p":              r.get("buyThr", 0),\n'
            '                "avg_sell_p":             r.get("sellThr", 0),\n'
            '                "total_charge_kwh":       r.get("totalChargeKwh", 0),\n'
            '                "total_discharge_kwh":    r.get("totalDischargeKwh", 0),\n'
            '            }\n'
)

if OLD_MODE_DICT in text:
    text = text.replace(OLD_MODE_DICT, NEW_MODE_DICT, 1)
    print('[OK]   server.py: dovecote_net_gbp + subscription_gbp added to mode dict')
elif 'dovecote_net_gbp' in text:
    print('[SKIP] server.py: dovecote_net already present')
else:
    print('[WARN] server.py: mode dict anchor not found')

# ── Patch 3: add vs_agile_dovecote_gbp to deltas block ───────────────────────

OLD_DELTA = (
    '    # Deltas vs agile baseline\n'
    '    if "agile" in results and "net_gbp" in results["agile"]:\n'
    '        base = results["agile"]["net_gbp"]\n'
    '        for mode in ("split", "optimise"):\n'
    '            if mode in results and "net_gbp" in results[mode]:\n'
    '                results[mode]["vs_agile_net_gbp"] = round(results[mode]["net_gbp"] - base, 2)\n'
)
NEW_DELTA = (
    '    # Deltas vs agile baseline\n'
    '    if "agile" in results and "net_gbp" in results["agile"]:\n'
    '        base_net      = results["agile"]["net_gbp"]\n'
    '        base_dovecote = results["agile"].get("dovecote_net_gbp", base_net)\n'
    '        for mode in ("split", "optimise"):\n'
    '            if mode in results and "net_gbp" in results[mode]:\n'
    '                results[mode]["vs_agile_net_gbp"]      = round(results[mode]["net_gbp"] - base_net, 2)\n'
    '                results[mode]["vs_agile_dovecote_gbp"] = round(results[mode].get("dovecote_net_gbp", 0) - base_dovecote, 2)\n'
)

if OLD_DELTA in text:
    text = text.replace(OLD_DELTA, NEW_DELTA, 1)
    print('[OK]   server.py: vs_agile_dovecote_gbp added to deltas')
elif 'vs_agile_dovecote_gbp' in text:
    print('[SKIP] server.py: dovecote delta already present')
else:
    print('[WARN] server.py: deltas anchor not found')

# ── Patch 4: add subscription_pcm to top-level payload ───────────────────────

OLD_PAYLOAD = (
    '    payload = {"modes": results, "months": months, "founder": founder,\n'
    '               "imp_mod_p": imp_mod, "exp_mod_p": exp_mod,\n'
    '               "sc_agile_p_day": sc_agile, "sc_eon_p_day": sc_eon,\n'
    '               "_ts": time.time()}\n'
)
NEW_PAYLOAD = (
    '    payload = {"modes": results, "months": months, "founder": founder,\n'
    '               "imp_mod_p": imp_mod, "exp_mod_p": exp_mod,\n'
    '               "sc_agile_p_day": sc_agile, "sc_eon_p_day": sc_eon,\n'
    '               "subscription_pcm": subscription_pcm,\n'
    '               "subscription_annual_gbp": round(subscription_pcm * 12, 2),\n'
    '               "_ts": time.time()}\n'
)

if OLD_PAYLOAD in text:
    text = text.replace(OLD_PAYLOAD, NEW_PAYLOAD, 1)
    print('[OK]   server.py: subscription_pcm added to compare payload')
elif '"subscription_pcm": subscription_pcm' in text:
    print('[SKIP] server.py: subscription already in payload')
else:
    print('[WARN] server.py: payload anchor not found')

SRV.write_text(text, 'utf-8')
print('\n[DONE] P&L fix applied. Restart: docker restart node3-portal')
print('       Then: curl "http://localhost:5000/api/backtest-compare?force=1"')

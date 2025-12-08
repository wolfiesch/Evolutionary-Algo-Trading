# Crypto System Maintenance Scripts

## Data Gap Verification

Check for data gaps in the candles database (useful after WebSocket disconnects):

### Local Usage
```bash
python crypto/scripts/check_data_gaps.py crypto/data/candles.db 2
```

### Fly.io Usage
```bash
fly ssh console -a crypto-alpha -C "python3 scripts/check_data_gaps.py data/candles.db 2"
```

**Arguments:**
- `db_path`: Path to SQLite database (required)
- `hours_back`: How many hours to scan (default: 2)

**What it checks:**
- Gaps > 5 minutes between consecutive candles
- Per-symbol gap detection
- Summary statistics (active symbols, total candles)

**Exit codes:**
- `0`: No gaps found
- `1`: Gaps detected (see output)

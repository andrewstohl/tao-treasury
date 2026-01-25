# TaoStats API Reference

## Base URL
```
https://api.taostats.io
```

## Authentication
- **Method:** API Key in header
- **Header:** `Authorization: <API_KEY>`

## Key Endpoints for TAO Treasury

### Account/Wallet Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/account/latest/v1` | GET | Get account balances and info |
| `/api/account/history/v1` | GET | Historical account data |

**Parameters for `/api/account/latest/v1`:**
- `address` (string) - SS58 or hex wallet address
- `network` (string) - "finney" (default), "nakamoto", "kusanagi"
- `page`, `limit` - Pagination (max 200 per page)

**Response includes:**
- `balance_free` - Liquid TAO (in rao, divide by 1e9 for TAO)
- `balance_staked` - Total staked
- `balance_staked_alpha_as_tao` - Alpha staked value
- `balance_staked_root` - Root subnet stake
- `balance_total` - Combined balance

---

### Stake/Position Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dtao/stake_balance/latest/v1` | GET | Current stake balances |
| `/api/dtao/stake_balance/history/v1` | GET | Historical stake (daily at midnight UTC) |
| `/api/dtao/stake_balance/portfolio/v1` | GET | Portfolio overview (**PRO subscription required**) |

**Parameters for history endpoint:**
- `address` - Wallet address
- `timestamp_start`, `timestamp_end` - Unix timestamps
- `block_start`, `block_end` - Block range

---

### Subnet Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/subnet/latest/v1` | GET | List all subnets with current metrics |
| `/api/subnet/info/v1` | GET | Detailed subnet info |

---

### dTAO Pool Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dtao/pool/latest/v1` | GET | Current pool liquidity for all subnets |
| `/api/dtao/pool/history/v1` | GET | Historical pool data |

**Pool data includes:**
- TAO reserves
- Alpha reserves
- Current price
- Liquidity metrics

---

### Slippage Calculation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dtao/slippage/v1` | GET | Estimate slippage for alpha/TAO transactions |

**Critical for:** Executable NAV calculations, position sizing

---

### Validator Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dtao/validator/latest/v1` | GET | Current validator metrics |
| `/api/dtao/validator/yield/latest/v1` | GET | Validator yield data |
| `/api/dtao/validator/history/v1` | GET | Historical validator data |

---

### Price Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/price/latest/v1` | GET | Current TAO price (USD) |
| `/api/price/history/v1` | GET | Historical prices |
| `/api/price/ohlc/v1` | GET | OHLC candlestick data |

---

## Response Format

All endpoints return paginated JSON:

```json
{
  "pagination": {
    "current_page": 1,
    "per_page": 50,
    "total_items": 100,
    "total_pages": 2,
    "next_page": 2,
    "prev_page": null
  },
  "data": [...]
}
```

## Units

- **Balances:** Returned in rao (1 TAO = 1,000,000,000 rao = 1e9 rao)
- **Timestamps:** ISO 8601 format
- **Addresses:** Available in both SS58 and hex format

## Rate Limiting

Not explicitly documented. Implement conservative rate limiting:
- Recommended: 60 requests/minute
- Use Redis caching to minimize API calls

## Notes

1. **PRO Subscription:** Some endpoints (like portfolio) require PRO
2. **Network:** Always use `network=finney` for mainnet
3. **Pagination:** Max 200 results per page
4. **Caching:** Pool and stake data can be cached for 2-5 minutes

## Sources

- [TaoStats API Docs](https://docs.taostats.io/docs/the-taostats-api)
- [API Reference](https://docs.taostats.io/reference/welcome-to-the-taostats-api)
- [Dashboard](https://dash.taostats.io/)

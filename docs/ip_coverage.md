# IP coverage

BIN: `./data/reference/IP-COUNTRY-REGION-CITY.BIN`

| Metric | Value |
|---|---:|
| Events with an IP string | 41,432,473 |
| Distinct IP strings | 3,239,628 |
| Events with public IPv4 | 41,422,559 |
| Events whose public IPv4 resolved | 40,966,752 |
| Resolve rate on public IPv4 | 98.90% |
| `checkout_success` events | 26,079 |
| `checkout_success` resolved | 25,860 |
| `checkout_success` resolve rate | 99.16% |

Private, loopback, and IPv6 addresses are stored in `ip_geo` with a status and are not sent to the BIN.
Join `glamira_raw.ip` to `ip_geo._id` for `country_code` and `city`.

## Top 10 country by event count

| Country | Events |
|---|---:|
| `DE` | 4,923,418 |
| `US` | 3,878,647 |
| `GB` | 2,941,540 |
| `IT` | 2,711,879 |
| `FR` | 2,280,724 |
| `NL` | 2,266,271 |
| `RO` | 1,355,940 |
| `ES` | 1,333,085 |
| `AU` | 1,219,647 |
| `SE` | 1,208,840 |

# Projector Compatibility

This app communicates with BenQ projectors using their built-in HTTP CGI interface. Projectors that share the same web interface platform (approximately 2012–2019) should be compatible.

---

## Confirmed Working

| Model | Firmware | Tested By | Date | Notes |
|-------|---------|-----------|------|-------|
| BenQ SH915 | V1.02 | [@fredhill](https://github.com/fredhill) | April 2026 | All features verified |

---

## Requirements

For a projector to work with this app it must have:

1. **LAN Control** enabled — found in the projector's Network Settings or Setup menu
2. **Connected to your local network** — via Ethernet or WiFi (model dependent)
3. **Network Standby** enabled — recommended, allows remote wake and status polling when off

---

## Likely Compatible

BenQ projectors from approximately 2012–2019 that use the same web interface platform are likely compatible. Indicators that your projector should work:

- Has a **LAN Control** or **Network Control** option in its menu
- Has a built-in web interface accessible at `http://<projector-ip>`
- Is from one of these series: **SH, SW, MH, MW, TH, W, MS, MX, MP**

Models in these series that are likely compatible (untested):

| Series | Example Models |
|--------|---------------|
| SH (Short throw) | SH940, SH960 |
| MH (Full HD) | MH856UST, MH760 |
| MW (WXGA) | MW855UST, MW769 |
| TH (Home theater) | TH671ST, TH681, TH683 |
| W (Home cinema) | W1070, W1080ST, W2000 |
| MS/MX (Business) | MS527, MX528, MX768 |

---

## Probably Not Compatible

- **Laser projectors (LK/LU series)** — different firmware architecture
- **Projectors older than ~2012** — may predate this web interface
- **Projectors without LAN Control** — no network interface to talk to
- **BenQ Interactive Flat Panels** — different product category entirely

---

## Reporting Compatibility

If you test this app with a projector not listed here, please [open a compatibility report](../../../issues/new?template=compatibility_report.md). Include:

- Model number and firmware version
- Which features worked or didn't work
- Any error messages

Every report helps expand the compatibility list for other users.

---

## Technical Background

The parameter IDs used by this app are mathematically derived from the projector's web interface firmware JavaScript files (see [API_REFERENCE.md](API_REFERENCE.md)). All projectors that share this firmware platform use the same parameter IDs, which is why compatibility is broad across the 2012–2019 range despite only being tested on one model.

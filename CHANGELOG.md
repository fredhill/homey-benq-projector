# Changelog

## 1.0.4 — 2026-05-18

### Fixed
- Fixed crash "Task exception was never retrieved" caused by unhandled exception in background model-detection task

## 1.0.2 — 2026-04-28

### Security
- Input validation on IP address field — only plain IPv4/IPv6 addresses accepted (prevents SSRF via hostnames or URLs)
- HTTP calls in device driver moved off the event loop via `run_in_executor` (prevents async blocking)
- HTTP session configured with `max_redirects=0` and `max_retries=0` to prevent redirect-based attacks and duplicate commands
- Response size cap (64 KB) before JSON parsing in both device and discovery code to prevent ReDoS
- Stronger projector fingerprinting in discovery — requires both `nPowerStatus` and `nLampHour` fields
- Fixed potential `NameError` in AMX discovery socket cleanup

### Store
- App tagline updated to "Cinema night, automated."
- README updated with cleaner description
- xlarge promotional images added for App Store listing

## 1.0.0 — 2026-04-21

Initial release.

### Features
- Power on/off with warm-up and cool-down state tracking
- Input source switching (HDMI 1, HDMI 2, Computer 1/2, Video, S-Video, USB Reader, Network Display)
- Volume control (slider + mute toggle)
- ECO Blank toggle — blanks screen and dims lamp to extend bulb life
- Picture mode switching (Dynamic, Presentation, sRGB, Cinema, 3D, User 1, User 2)
- Lamp hours monitoring with Homey Insights logging
- Lamp warning threshold — configurable alert when hours exceed a set value
- Power state capability with four states: On, Warming Up, Cooling Down, Standby
- Automatic projector discovery via AMX UDP broadcast (fast) with subnet scan fallback
- Manual IP entry fallback for networks where discovery is restricted
- Network Standby mode setting — treats connection timeouts as off rather than errors when disabled
- Configurable status poll interval (30–600 seconds)
- Model detection and feature probing at startup
- Automatic capability injection for existing devices when new features are added (no re-pairing required)

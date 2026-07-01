# Changelog

## 1.0.9 — 2026-07-01

### Fixed
- Fixed the projector randomly dropping to "unavailable" every few minutes. The HTTP session kept a keep-alive connection open between status polls, but the projector's embedded server drops idle connections — so the reused socket went stale and polls failed. Each request now uses a fresh connection (Connection: close).
- Properly fixed the recurring "Task exception was never retrieved" crash. The SDK runs set_available/set_unavailable as detached background tasks, so their failures cannot be caught with try/except. Added an event-loop exception handler that swallows these specific SDK-internal availability errors while still reporting all other errors normally.

## 1.0.8 — 2026-06-12

### Added
- Flow action cards: Set input source, Set picture mode, Turn ECO Blank on/off
- Flow trigger cards: Input source changed, Power state changed, Picture mode changed, Lamp warning threshold reached (with tags)
- Flow condition cards: Input source is, Power state is, Picture mode is

### Fixed
- Hardened availability reporting against an SDK-internal crash seen on Homey v13.3.0-rc firmware — set_available/set_unavailable are now guarded and only called on state transitions

## 1.0.5 — 2026-05-18

### Fixed
- Fixed crash "Task exception was never retrieved" — exceptions raised by Homey's set_unavailable inside the poll task now can't escape the interval handler
- Fixed same class of crash in background model-detection task (ensure_future)

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

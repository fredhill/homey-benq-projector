# Project History & Developer Handoff

**App:** BenQ Network Projector for Homey
**App ID:** `com.fredhill.benq-projector`
**Repo:** https://github.com/fredhill/homey-benq-projector
**Store:** https://homey.app/a/com.fredhill.benq-projector
**Author:** Danny Dehaze (fredhill@mac.com)
**Current version:** 1.0.11
**Last updated:** 2026-09-19

---

## 1. Purpose of this document

This is the orientation document for anyone picking up this app. It covers *why*
the project exists, what was built, what was tried and rejected, and — most
importantly — the **hard-won lessons** that are not obvious from reading the code.

It deliberately does **not** duplicate:

| Topic | See instead |
|---|---|
| The BenQ HTTP CGI protocol, command codes, parameter IDs | [`API_REFERENCE.md`](API_REFERENCE.md) |
| Which projector models work | [`COMPATIBILITY.md`](COMPATIBILITY.md) |
| End-user install & feature overview | [`../README.md`](../README.md) |
| Release-by-release detail | [`../CHANGELOG.md`](../CHANGELOG.md) |

Read section **6 (Lessons Learned)** before changing anything. Several of the
bugs in this app's history were fixed *incorrectly* two or three times because
the underlying mechanism wasn't understood.

---

## 2. The original idea

The goal was simple and personal: control a **BenQ SH915 projector** in a home
theater from Homey, so that "movie night" could be one automation instead of
hunting for a remote — lights down, projector on, correct input selected.

Two constraints shaped everything:

1. **Local network only.** No cloud, no vendor account, no IR blaster. The
   projector already has a LAN control interface; use it.
2. **No extra hardware.** Anything requiring a bridge device was out of scope.

The projector exposes an undocumented HTTP CGI interface. Most of the early work
was reverse-engineering it (captured in `API_REFERENCE.md`).

---

## 3. Scope

### In scope (built and shipped)
- Power on/off, including the projector's warm-up and cool-down states
- Input source switching (HDMI 1/2, Computer 1/2, Video, S-Video, USB Reader, Network Display)
- Volume set + mute
- ECO Blank (blanks screen, dims lamp — extends bulb life during pauses)
- Picture mode (Dynamic, Presentation, sRGB, Cinema, 3D, User 1/2)
- Lamp hour monitoring + Insights logging + configurable replacement warning
- Auto-discovery (AMX UDP broadcast, with subnet-scan fallback) and manual IP entry
- Full Flow support: triggers, conditions, and actions

### Explicitly out of scope
- **Cloud/remote control.** Local network only, by design.
- **Non-network BenQ models.** Serial/IR-only projectors are not supported and
  won't be — see `COMPATIBILITY.md`.
- **Restoring projector state after a restart.** Deliberately rejected; see §6.5.
  The app *reports* state and lets Flows decide. It never actuates hardware on
  its own initiative.

### Tried and abandoned
- **Reading the projector's model name for the device title.** The bulk status
  endpoint doesn't include it. A dedicated CGI parameter and HTML page scraping
  were both attempted and failed. The code was reverted; devices fall back to
  "BenQ Projector". Don't spend time here again without new protocol information.
- **A custom "Toggle mute" Flow card.** Homey auto-generates three mute cards
  from the standard `volume_mute` capability; a fourth was redundant and was
  removed in v1.0.8's follow-up.

---

## 4. Architecture

### File map

```
app.py                                  App class; Flow action/condition run
                                        listeners; asyncio exception guard (§6.4)
drivers/benq-sh915/
  driver.py                             Pairing + discovery (AMX UDP, subnet scan)
  device.py                             The core. Polling, capabilities, commands,
                                        Flow triggers, restart guard (§6.5)
  driver.compose.json                   Capabilities, settings, pair flow, images
.homeycompose/
  app.json                              App manifest (id, version, metadata)
  capabilities/*.json                   5 custom capabilities
  flow/{triggers,conditions,actions}/   10 Flow cards
assets/                                 App icon + store images + capability icons
docs/                                   Protocol, compatibility, this file
```

### How it works

**Discovery** (`driver.py`) runs two stages: AMX UDP broadcast on port 9131
(fast, ~2s, only works if AMX is enabled on the projector), falling back to a
threaded /24 subnet scan (~15s). Candidates are fingerprinted by requiring both
`nPowerStatus` and `nLampHour` in the status response. A manual-entry fallback
device is always offered so pairing can't dead-end.

**Polling** (`device.py`) hits one bulk status endpoint on an interval
(default 120s, user-configurable 30–600s) and derives power state, lamp hours,
input source, and picture mode from a single response. Warm-up and cool-down
states schedule an extra 30s re-poll so transitions are tracked promptly. An
immediate poll fires ~3s after init so the tile reflects reality quickly after
a restart.

**Custom capabilities:** `power_state` (enum: on/warming/cooling/standby),
`input_source`, `picture_mode`, `lamp_hours` (number, Insights-logged),
`eco_blank` (boolean). Capability order in `driver.compose.json` controls which
one the mobile app shows by default — `input_source` is deliberately second
(after `onoff`) so it is the default mobile view.

**Flow cards:** actions and conditions register their run listeners in `app.py`
and receive the device as `args["device"]`; triggers are fired from `device.py`
on state change via `get_device_trigger_card(...).trigger(...)`.

**Capability self-healing:** `_ensure_capability()` adds newly-introduced
capabilities to already-paired devices, so users never have to re-pair.

---

## 5. Version history

| Version | Date | What happened |
|---|---|---|
| 1.0.0 | 2026-04-21 | Initial release. All core features. |
| 1.0.1 | 2026-04 | App Store review fixes: distinct driver icon, shorter description. |
| 1.0.2/1.0.3 | 2026-04-28 | Security pass (see below). Store polish, xlarge images, tagline. |
| 1.0.4–1.0.6 | 2026-05/06 | Repeated attempts at the "Task exception was never retrieved" crash. **Both wrong** — see §6.4. |
| 1.0.7 | 2026-06 | Capability icons (power/input/picture); reordered so Input Source is the default mobile view. |
| 1.0.8 | 2026-06-12 | Full Flow card set: 3 actions, 4 triggers, 3 conditions. |
| 1.0.9 | 2026-07-01 | **Two real fixes:** keep-alive dropout (§6.3) and the *correct* crash fix (§6.4). |
| 1.0.10 | 2026-09-04 | First attempt at the restart power-on bug — a 15s time guard. Insufficient. |
| 1.0.11 | 2026-09-11 | **Correct** restart fix: restore-echo detection, no timing race (§6.5). |

**Security pass (1.0.2)** — worth knowing since these constraints still apply:
IP input is validated with `ipaddress.ip_address()` (blocks SSRF via hostnames,
ports, credentials, paths); HTTP runs in `run_in_executor` so it never blocks the
event loop; the session uses `max_redirects=0` and `max_retries=0` (retries would
send duplicate commands to the projector); responses are size-capped at 64 KB
before regex/JSON parsing.

**Adoption:** ~12 live installs as of late 2026. Small, niche, but real users —
several crash reports in this history came from them, not from the author.

---

## 6. Lessons learned (read this)

### 6.1 The projector's HTTP server is not standards-compliant
It returns **JSON with trailing commas** (stripped by regex before parsing) and
**malformed HTTP headers** that make `requests` raise. Throughout the code you'll
see `if "header" in str(e).lower():` — these are *expected* and treated as
success, not errors. Don't "clean this up" without understanding it.

### 6.2 Homey renders SVG icons as flat white silhouettes
Every fill becomes white. Colour is impossible. To get visible detail you must
use an SVG `<mask>` with black shapes to punch **transparent** holes, letting the
`brandColor` background show through. This is why the icons look the way they do.
`brandColor` is `#7c3aed` (BenQ purple) so the icon circle isn't a white blob.

### 6.3 Never hold a keep-alive connection to the projector
`requests.Session` pools TCP connections by default. The projector's embedded
server silently drops idle connections, so the next poll reuses a dead socket and
fails. Three failures marked the device **unavailable** — which is why it "flapped"
every few minutes and a restart temporarily fixed it. The session now sends
`Connection: close`. **Do not remove this.**

### 6.4 `set_available` / `set_unavailable` crashes cannot be caught with try/except
The Python SDK runs them as **detached background asyncio tasks**. The `await`
returns immediately; the failure happens later in a task nobody retrieves,
surfacing as `Unhandled Rejection "Task exception was never retrieved"`.

This was "fixed" wrongly **twice** (v1.0.5 wrapped the poll, v1.0.8 wrapped the
calls) before the mechanism was understood. The only thing that works is an
**event-loop exception handler** that inspects the traceback for SDK availability
frames and swallows just those — implemented as `_install_exception_guard()` in
`app.py`. Availability calls are also change-only (tracked in `_marked_available`)
so the buggy path runs as rarely as possible.

### 6.5 Homey re-delivers stored capability values after a restart
On restart, Homey replays the last stored `onoff` value to the capability
listener to "restore" device state. The app couldn't distinguish that from a real
button press, so **the projector switched itself on** whenever the server rebooted.
Real-world impact: it was discovered by walking into the basement and finding the
projector had been running for a day.

v1.0.10 tried a 15-second guard window. That's a **race**, and a slow
firmware-update reboot loses it — the restore arrives after the window expires.

v1.0.11 added a timing-independent check: the app records the `onoff` value Homey
holds at init, and ignores any later command that merely *repeats* it. The logic
is that **a person toggling the tile always asks for the opposite of what's
displayed**, so a repeat can only be a restore echo. The echo disarms once
consumed or once a poll confirms real state, so genuine presses and Flows still
work. See `_is_restart_echo()` in `device.py`.

**Design principle established here:** the app reports state; Flows decide
actions. The app must never actuate hardware on its own initiative. A "restore
last state" setting was explicitly considered and rejected.

### 6.6 Many "crash reports" are Homey Self-Hosted environment issues, not app bugs
Two reports looked alarming but contained **zero app frames** — the stack was
entirely inside Homey's own runtime (`homey-local/lib/AppLocal.mts`), failing
before any Python loaded:

- **`Could not mount /dev/random : 32`** — Homey Self-Hosted in an *unprivileged*
  LXC container. Python apps need a sandbox; unprivileged LXC blocks the device
  mount. Fix is on the user's side (privileged container). Affects every Python
  app, not just this one.
- **`uv_pipe_chmod EINVAL`** — Homey can't `chmod` the Unix domain socket it
  creates per app, because the data directory sits on a filesystem that doesn't
  support it (network share / incompatible bind mount).

**How to triage:** if `Homey Model ID` is `shs` (Self-Hosted) and the stack trace
has no app frames, it's an environment problem. Reply to the user with the fix;
don't ship code.

### 6.7 Development environment gotchas
- **Docker is not installed** on the dev Mac. Use `npx homey app install`, never
  `npx homey app run` (which requires Docker).
- **Build from local disk, never the NAS.** The project once lived on an SMB
  share; the Homey CLI couldn't clean its `.homeybuild` cache there (`ENOTEMPTY`)
  and every file showed as modified (filemode `755` vs `644`). Git works on the
  share, the CLI does not. Canonical working copy:
  `/Users/fredhill/homey-dev/benq-sh915-projector`.
- **`python_packages/` is gitignored** and not in the repo. A fresh clone can't
  build without Docker — copy `python_packages/` from an existing working copy.
- **A macOS update can silently break git.** After a major OS update the Apple
  git shim refuses to run until the Xcode licence is re-accepted
  (`You have not agreed to the Xcode license agreements`). Fix:
  `sudo xcodebuild -license` (needs admin). Worth knowing because it also blocks
  `npx homey app publish`, which performs a git commit/tag/push — so a release
  can fail for reasons that have nothing to do with the app. Hit and resolved
  on 2026-09-19.

---

## 7. Development workflow

```bash
cd /Users/fredhill/homey-dev/benq-sh915-projector

npx homey app validate --level publish   # always before shipping
npx homey app install                    # deploy to Homey for testing
npx homey app publish                    # bump version, upload a build
```

`publish` prompts to **commit** the version bump and **push** to origin — answer
**yes to both**, or the repo drifts from what's on the store. After uploading it
prints a dashboard URL; the build must then be promoted to Test/Live there.

Both `app.py` and `drivers/benq-sh915/device.py` should compile clean:
`python3 -m py_compile app.py drivers/benq-sh915/device.py`. The `homey` module
is injected by the runtime and is **not** importable locally, so unit-testing
logic means extracting it into pure functions (as done for the restart-echo
decision table).

---

## 8. Known issues and open items

- **Stale "on" tile when unreachable.** If the projector is off *and* not
  answering (network standby disabled or unresponsive), poll failures mark the
  device unavailable but deliberately don't claim it's off — so the tile can keep
  showing "on". Cosmetic only since v1.0.11 (a stale value can no longer cause a
  power-on), but it could be improved by reporting `standby` once the device is
  marked unavailable.
- **Mute cards are ambiguous.** The projector only exposes a *toggle* command, so
  Homey's separate "Mute"/"Unmute" cards both send the same toggle and can appear
  inverted if state drifts. "Toggle muted volume on or off" is the honest one.
- **Restore-echo edge case.** An intentional "when Homey starts, turn on the
  projector" Flow would be suppressed if it fires during the guard. This is the
  accepted trade-off (see §6.5).
- **Compatibility is thin.** Only the SH915 is confirmed. Collecting
  "works on my model" reports and folding them into `COMPATIBILITY.md` is the
  highest-value low-effort work available.

### Ideas not yet built
- An "app started" Flow trigger exposing the last known power state as a token,
  so Flows could decide whether to restore — considered, deferred (§6.5).
- A runtime safety net: notify (or auto-off) if the projector has been on for
  more than N hours. Buildable today with existing Flow cards; could be a
  built-in convenience.

---

## 9. Support playbook

Crash/diagnostic reports arrive by email from Homey and can be answered by
replying directly.

1. **Check `Homey Model ID`.** `shs` = Self-Hosted → suspect environment (§6.6).
2. **Look for app frames in the stack.** No Python frames = not our bug.
3. **`Task exception was never retrieved`** → availability path (§6.4).
4. **"Unavailable every few minutes"** → connection reuse (§6.3).
5. **"Turns on by itself"** → restart state-restore (§6.5).

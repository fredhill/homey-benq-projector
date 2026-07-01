import asyncio
import ipaddress
import json
import re
import requests
from homey.device import Device

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

POWER_ON      = 0
POWER_STANDBY = 6
POWER_WARMING = 7
POWER_COOLING = 8

LAMP_RATED_HOURS = {0: 3500, 1: 5000, 2: 5000, 3: 6000, 4: 5000}

# Human-readable names for flow trigger tokens
INPUT_NAMES = {
    "5": "HDMI 1", "22": "HDMI 2", "0": "Computer 1", "13": "Computer 2",
    "1": "Video", "2": "S-Video", "17": "USB Reader", "18": "Network Display",
}
PICTURE_NAMES = {
    "0": "Dynamic", "1": "Presentation", "2": "sRGB", "3": "Cinema",
    "4": "3D", "5": "User 1", "6": "User 2",
}
POWER_NAMES = {
    "on": "On", "warming": "Warming Up", "cooling": "Cooling Down", "standby": "Standby",
}

DEFAULT_POLL_INTERVAL    = 120
DEFAULT_LAMP_WARNING     = 3000
DEFAULT_NETWORK_STANDBY  = True

_RESPONSE_SIZE_LIMIT = 65536   # 64 KB — BenQ responses are typically < 1 KB


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _parse_benq_json(response):
    """BenQ returns trailing commas in JSON arrays — strip before parsing."""
    if len(response.text) > _RESPONSE_SIZE_LIMIT:
        raise ValueError("Response too large")
    text = re.sub(r',\s*([}\]])', r'\1', response.text)
    return json.loads(text)


def _validate_ip(ip: str) -> str:
    """
    Validate that ip is a plain IPv4/IPv6 address.
    Rejects hostnames, embedded credentials, ports, paths, and fragments.
    Raises ValueError on anything invalid.
    """
    if not ip:
        return ip   # empty = not yet configured, allowed
    ipaddress.ip_address(ip)
    return ip


def _clamp(value, lo, hi, default):
    """Return value clamped to [lo, hi], falling back to default on error."""
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────
# Device
# ──────────────────────────────────────────────

class BenQSH915Device(Device):

    async def on_init(self):
        await super().on_init()
        self.log("BenQ projector device initialized")

        # Session with safe defaults — no redirects, no automatic retries
        # (retries would send duplicate commands to the projector)
        self._session = requests.Session()
        self._session.max_redirects = 0
        adapter = requests.adapters.HTTPAdapter(max_retries=0)
        self._session.mount('http://', adapter)
        # The projector's embedded HTTP server drops idle keep-alive
        # connections, so a pooled socket goes stale between polls and the
        # next request fails — which is what made the device flap to
        # "unavailable" every few minutes. Force a fresh connection per
        # request with Connection: close.
        self._session.headers.update({"Connection": "close"})

        settings = self.get_settings()
        try:
            self._ip = _validate_ip(settings.get("ip_address", ""))
        except ValueError:
            self._ip = ""
            self.error("Stored IP address is invalid — please update device settings")

        self._poll_interval      = _clamp(settings.get("poll_interval"),      30,  600,  DEFAULT_POLL_INTERVAL)
        self._lamp_warning_hours = _clamp(settings.get("lamp_warning_hours"), 100, 6000, DEFAULT_LAMP_WARNING)
        self._network_standby    = bool(settings.get("network_standby", DEFAULT_NETWORK_STANDBY))
        self._fail_count         = 0
        self._feature_profile    = {}
        self._eco_blank          = False   # tracked locally (BenQ only has toggle)
        self._marked_available   = None    # last availability we reported (None = unknown)

        # Flow trigger state — last-known values so we only fire on change
        self._prev_power         = None
        self._prev_input         = None
        self._prev_picture       = None
        self._lamp_warning_fired = False

        # Device flow trigger cards
        self._trig_power   = self.homey.flow.get_device_trigger_card("power_state_changed")
        self._trig_input   = self.homey.flow.get_device_trigger_card("input_source_changed")
        self._trig_picture = self.homey.flow.get_device_trigger_card("picture_mode_changed")
        self._trig_lamp    = self.homey.flow.get_device_trigger_card("lamp_warning")

        self.register_capability_listener("onoff",        self._on_onoff)
        self.register_capability_listener("input_source", self._on_input_source)
        self.register_capability_listener("volume_set",   self._on_volume_set)
        self.register_capability_listener("volume_mute",  self._on_volume_mute)

        # Add new capabilities to existing devices without requiring re-pairing
        for cap in ["eco_blank", "picture_mode"]:
            await self._ensure_capability(cap)
        self.register_capability_listener("eco_blank",    self._on_eco_blank)
        self.register_capability_listener("picture_mode", self._on_picture_mode)

        self.homey.set_interval(self._poll, self._poll_interval * 1000)
        self.log(f"Polling every {self._poll_interval}s | "
                 f"Lamp warning at {self._lamp_warning_hours}h | "
                 f"Network standby: {self._network_standby}")

        # Detect model in background — non-blocking, won't affect startup
        task = asyncio.ensure_future(self._detect_model())
        task.add_done_callback(self._on_background_task_done)

    async def on_settings(self, old_settings, new_settings, changed_keys):
        if "ip_address" in changed_keys:
            try:
                self._ip = _validate_ip(new_settings["ip_address"])
            except ValueError:
                raise ValueError("Invalid IP address — enter a plain IPv4 or IPv6 address")
        if "poll_interval" in changed_keys:
            self._poll_interval = _clamp(new_settings["poll_interval"], 30, 600, DEFAULT_POLL_INTERVAL)
        if "lamp_warning_hours" in changed_keys:
            self._lamp_warning_hours = _clamp(new_settings["lamp_warning_hours"], 100, 6000, DEFAULT_LAMP_WARNING)
        if "network_standby" in changed_keys:
            self._network_standby = bool(new_settings["network_standby"])

    # ------------------------------------------------------------------
    # HTTP helper — runs blocking requests in a thread so the async
    # event loop is never blocked, even during long timeouts
    # ------------------------------------------------------------------

    async def _post(self, url, timeout=5):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._session.post(url, timeout=timeout, allow_redirects=False)
        )

    # ------------------------------------------------------------------
    # Capability management
    # ------------------------------------------------------------------

    async def _ensure_capability(self, cap_id):
        """Add capability if not already present — avoids needing to re-pair."""
        try:
            if not self.has_capability(cap_id):
                await self.add_capability(cap_id)
                self.log(f"Added new capability: {cap_id}")
        except Exception as e:
            self.log(f"Could not add capability '{cap_id}': {e}")

    # ------------------------------------------------------------------
    # Model detection & feature probing
    # ------------------------------------------------------------------

    def _on_background_task_done(self, task):
        """Retrieve background task result so Python never logs 'Task exception was never retrieved'."""
        try:
            task.result()
        except Exception:
            pass   # already logged inside the task itself

    async def _detect_model(self):
        """Query projector identity and probe supported features. Runs once at startup."""
        try:
            url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576"
            response = await self._post(url)
            status = _parse_benq_json(response)[0]

            model = status.get('acProjectorName', 'Unknown')
            fw    = status.get('acProjectorFWVersion', 'Unknown')
            self.log(f"Model: {model} | Firmware: {fw}")

            self._feature_profile = await self._probe_features()
            self.log(f"Feature profile: {self._feature_profile}")

        except Exception:
            self.log("Model detection skipped — using defaults")

    async def _probe_features(self):
        """
        Test each optional feature category against the live projector.
        Returns a dict of feature_name -> bool/value.
        """
        profile = {
            'volume':        False,
            'volume_max':    10,
            'volume_min':    0,
            'input':         True,   # confirmed on SH915
            'lamp_mode':     True,   # confirmed on SH915
            'picture_mode':  True,   # confirmed on SH915
            'eco_blank':     True,   # confirmed on SH915
            'freeze':        True,   # confirmed on SH915
        }

        # Volume range query — c:9 returns {"min": 0, "max": 10}
        try:
            url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:9,p:917516"
            r = await self._post(url, timeout=3)
            data = _parse_benq_json(r)[0]
            if 'max' in data:
                profile['volume']     = True
                profile['volume_max'] = int(data['max'])
                profile['volume_min'] = int(data.get('min', 0))
                self.log(f"Volume range confirmed: {profile['volume_min']}–{profile['volume_max']}")
        except Exception:
            pass

        return profile

    async def _safe_execute(self, feature_name, coro):
        """
        Run an awaitable. If the feature is known unsupported, skip it.
        Logs errors without crashing the device.
        """
        if feature_name in self._feature_profile and not self._feature_profile[feature_name]:
            return None
        try:
            return await coro
        except Exception as e:
            self.error(f"Feature '{feature_name}' failed")
            return None

    # ------------------------------------------------------------------
    # Availability — guarded and change-only.
    # The SDK's set_unavailable can raise from an internal background task
    # (seen on Homey v13.3.0-rc firmware), so never let it propagate and
    # never call it more often than needed.
    # ------------------------------------------------------------------

    async def _mark_available(self):
        if self._marked_available is True:
            return
        try:
            await self.set_available()
            self._marked_available = True
        except Exception:
            self.log("set_available failed — will retry on next poll")

    async def _mark_unavailable(self, message):
        if self._marked_available is False:
            return
        try:
            await self.set_unavailable(message)
            self._marked_available = False
        except Exception:
            self.log("set_unavailable failed — will retry on next poll")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll(self):
        """Bulk status poll — one HTTP call covers power, lamp hours, source."""
        try:
            await self._poll_inner()
        except Exception:
            pass   # Safety net — set_interval tasks must never raise

    async def _poll_inner(self):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576"
        try:
            response = await self._post(url)
            data = _parse_benq_json(response)[0]
            self._fail_count = 0
            await self._apply_bulk_status(data)
            await self._mark_available()

        except requests.exceptions.ConnectionError:
            if self._network_standby:
                await self._on_poll_failure("connection refused")
            else:
                # Projector is simply off — not a failure
                await self.set_capability_value("onoff", False)
                await self.set_capability_value("power_state", "standby")

        except requests.exceptions.Timeout:
            if self._network_standby:
                await self._on_poll_failure("timeout")
            else:
                await self.set_capability_value("onoff", False)
                await self.set_capability_value("power_state", "standby")

        except Exception as e:
            if "header" in str(e).lower():
                return  # Expected BenQ malformed header — not a real error
            await self._on_poll_failure("unexpected error")

    async def _apply_bulk_status(self, data):
        power = data.get("nPowerStatus")

        # Power state
        if power == POWER_ON:
            await self.set_capability_value("onoff", True)
            await self._set_power_state("on")
        elif power == POWER_WARMING:
            await self.set_capability_value("onoff", True)
            await self._set_power_state("warming")
            self.homey.set_timeout(self._poll, 30 * 1000)   # re-poll in 30s
        elif power == POWER_COOLING:
            await self.set_capability_value("onoff", False)
            await self._set_power_state("cooling")
            self.homey.set_timeout(self._poll, 30 * 1000)   # re-poll in 30s
        else:
            await self.set_capability_value("onoff", False)
            await self._set_power_state("standby")

        # Lamp hours — readable in all states including standby
        lamp_hours = data.get("nLampHour")
        if lamp_hours is not None:
            await self.set_capability_value("lamp_hours", lamp_hours)
            lamp_mode = data.get("nLampMode", 0)
            rated     = LAMP_RATED_HOURS.get(lamp_mode, 3500)
            pct       = round(lamp_hours / rated * 100)
            self.log(f"Lamp: {lamp_hours}h / {rated}h rated ({pct}%)")
            if lamp_hours >= rated - 200:
                self.error(f"URGENT: lamp at {lamp_hours}h — replace soon!")
            elif lamp_hours >= self._lamp_warning_hours:
                self.log(f"WARNING: lamp at {lamp_hours}h — past warning threshold of {self._lamp_warning_hours}h")
            await self._check_lamp_warning(lamp_hours)

        # Input source, picture mode, and volume — only meaningful when fully on
        if power == POWER_ON:
            source_id = data.get("nPWSourceID")
            if source_id is not None:
                await self._set_input_value(str(source_id))

            picture_mode = data.get("nPictureMode")
            if picture_mode is not None:
                await self._set_picture_value(str(picture_mode))

            await self._poll_volume()

    async def _poll_volume(self):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:917516"
        try:
            response = await self._post(url, timeout=3)
            level = _parse_benq_json(response)[0]["value"]   # 0-10
            await self.set_capability_value("volume_set", level / 10)
        except Exception:
            pass   # non-critical; slider just won't update

    async def _on_poll_failure(self, reason):
        self._fail_count += 1
        self.error(f"Poll failed ({self._fail_count}): {reason}")
        if self._fail_count >= 3:
            await self._mark_unavailable("Projector unreachable")

    # ------------------------------------------------------------------
    # State setters that also fire flow triggers on change
    # ------------------------------------------------------------------

    async def _set_power_state(self, new):
        await self.set_capability_value("power_state", new)
        if self._prev_power is not None and self._prev_power != new:
            try:
                await self._trig_power.trigger(self, {"state": POWER_NAMES.get(new, new)})
            except Exception:
                pass
        self._prev_power = new

    async def _set_input_value(self, new):
        await self.set_capability_value("input_source", new)
        if self._prev_input is not None and self._prev_input != new:
            try:
                await self._trig_input.trigger(self, {"source": INPUT_NAMES.get(new, new)})
            except Exception:
                pass
        self._prev_input = new

    async def _set_picture_value(self, new):
        await self.set_capability_value("picture_mode", new)
        if self._prev_picture is not None and self._prev_picture != new:
            try:
                await self._trig_picture.trigger(self, {"mode": PICTURE_NAMES.get(new, new)})
            except Exception:
                pass
        self._prev_picture = new

    async def _check_lamp_warning(self, lamp_hours):
        """Fire the lamp-warning trigger once when crossing the threshold."""
        if lamp_hours >= self._lamp_warning_hours:
            if not self._lamp_warning_fired:
                self._lamp_warning_fired = True
                try:
                    await self._trig_lamp.trigger(self, {"lamp_hours": lamp_hours})
                except Exception:
                    pass
        else:
            self._lamp_warning_fired = False   # reset if lamp counter drops (e.g. lamp reset)

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------

    async def _on_onoff(self, value, opts=None):
        if value:
            await self._turn_on()
        else:
            await self._turn_off()

    async def _turn_on(self):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851977,v:9"
        try:
            self.log("Sending power ON command")
            await self._post(url)
            await self.set_capability_value("onoff", True)
            await self._set_power_state("warming")
            await self._mark_available()
            self.log("Power ON sent — projector warming up")
        except requests.exceptions.Timeout:
            self.error("Power ON timed out")
            raise Exception("Projector did not respond")
        except Exception as e:
            if "header" in str(e).lower():
                await self.set_capability_value("onoff", True)
                await self._set_power_state("warming")
                await self._mark_available()
                self.log("Power ON sent (header error ignored)")
            else:
                self.error("Power ON failed")
                raise

    async def _turn_off(self):
        base  = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf"
        steps = [
            "?&t:26,c:6,p:851982",
            "?&t:26,c:5,p:851977,v:9",
            "?&t:26,c:6,p:851982",
            "?&t:26,c:5,p:851977,v:9",
            "?&t:26,c:6,p:1012",
        ]
        try:
            self.log("Sending power OFF sequence (5 steps)")
            for i, step in enumerate(steps, 1):
                await self._post(base + step)
                self.log(f"Step {i}/5 sent")
                if i < len(steps):
                    await asyncio.sleep(0.5)
            await self.set_capability_value("onoff", False)
            await self._set_power_state("cooling")
            self.log("Power OFF sequence complete — projector cooling")
        except Exception as e:
            if "header" in str(e).lower():
                await self.set_capability_value("onoff", False)
                await self._set_power_state("cooling")
                self.log("Power OFF sent (header error ignored)")
            else:
                self.error("Power OFF failed")
                raise

    # ------------------------------------------------------------------
    # Input source
    # ------------------------------------------------------------------

    async def _on_input_source(self, value, opts=None):
        """value is string source ID e.g. '5' for HDMI 1."""
        source_id = int(value)
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917504,v:{source_id}"
        try:
            await self._post(url)
            self.log(f"Input switched to source {source_id}")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error("Input switch failed")
                raise

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    async def _on_volume_set(self, value, opts=None):
        """value is 0.0-1.0 from Homey; projector expects 0-10."""
        level = round(value * 10)
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917516,v:{level}"
        try:
            await self._post(url)
            self.log(f"Volume set to {level}/10")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error("Volume set failed")

    async def _on_volume_mute(self, value, opts=None):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851980,v:12"
        try:
            await self._post(url)
            self.log(f"Mute {'on' if value else 'off'} (toggle sent)")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error("Mute toggle failed")

    # ------------------------------------------------------------------
    # ECO Blank
    # ------------------------------------------------------------------

    async def _on_eco_blank(self, value, opts=None):
        """
        BenQ only has a toggle command — no separate on/off.
        We track local state and only send the toggle when needed.
        """
        if value == self._eco_blank:
            return  # Already in the desired state, nothing to do
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851974,v:6"
        try:
            await self._post(url)
            self._eco_blank = value
            self.log(f"ECO Blank {'on' if value else 'off'}")
        except Exception as e:
            if "header" in str(e).lower():
                self._eco_blank = value
                self.log(f"ECO Blank {'on' if value else 'off'} (header error ignored)")
            else:
                self.error("ECO Blank failed")
                raise

    # ------------------------------------------------------------------
    # Picture mode
    # ------------------------------------------------------------------

    async def _on_picture_mode(self, value, opts=None):
        """value is string mode ID e.g. '3' for Cinema."""
        mode_id = int(value)
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:983040,v:{mode_id}"
        try:
            await self._post(url)
            self.log(f"Picture mode set to {mode_id}")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error("Picture mode failed")
                raise

    # ------------------------------------------------------------------
    # Flow action entry points — called from app.py run listeners.
    # Each sends the command and updates the capability so the UI reflects it.
    # ------------------------------------------------------------------

    async def flow_set_input_source(self, source_id):
        await self._on_input_source(source_id)
        await self._set_input_value(str(source_id))

    async def flow_set_picture_mode(self, mode_id):
        await self._on_picture_mode(mode_id)
        await self._set_picture_value(str(mode_id))

    async def flow_set_eco_blank(self, on):
        await self._on_eco_blank(on)
        await self.set_capability_value("eco_blank", on)


homey_export = BenQSH915Device

import asyncio
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

DEFAULT_POLL_INTERVAL    = 120
DEFAULT_LAMP_WARNING     = 3000
DEFAULT_NETWORK_STANDBY  = True


# ──────────────────────────────────────────────
# JSON helper
# ──────────────────────────────────────────────

def _parse_benq_json(response):
    """BenQ returns trailing commas in JSON arrays — strip before parsing."""
    text = re.sub(r',\s*([}\]])', r'\1', response.text)
    return json.loads(text)


# ──────────────────────────────────────────────
# Device
# ──────────────────────────────────────────────

class BenQSH915Device(Device):

    async def on_init(self):
        await super().on_init()
        self.log("BenQ projector device initialized")

        settings = self.get_settings()
        self._ip                  = settings.get("ip_address", "10.50.0.29")
        self._poll_interval       = int(settings.get("poll_interval", DEFAULT_POLL_INTERVAL))
        self._lamp_warning_hours  = int(settings.get("lamp_warning_hours", DEFAULT_LAMP_WARNING))
        self._network_standby     = bool(settings.get("network_standby", DEFAULT_NETWORK_STANDBY))
        self._fail_count          = 0
        self._feature_profile     = {}

        self.register_capability_listener("onoff",        self._on_onoff)
        self.register_capability_listener("input_source", self._on_input_source)
        self.register_capability_listener("volume_set",   self._on_volume_set)
        self.register_capability_listener("volume_mute",  self._on_volume_mute)

        self.homey.set_interval(self._poll, self._poll_interval * 1000)
        self.log(f"Polling every {self._poll_interval}s | "
                 f"Lamp warning at {self._lamp_warning_hours}h | "
                 f"Network standby: {self._network_standby}")

        # Detect model in background — non-blocking, won't affect startup
        asyncio.ensure_future(self._detect_model())

    async def on_settings(self, old_settings, new_settings, changed_keys):
        if "ip_address"          in changed_keys:
            self._ip = new_settings["ip_address"]
        if "poll_interval"       in changed_keys:
            self._poll_interval = int(new_settings["poll_interval"])
        if "lamp_warning_hours"  in changed_keys:
            self._lamp_warning_hours = int(new_settings["lamp_warning_hours"])
        if "network_standby"     in changed_keys:
            self._network_standby = bool(new_settings["network_standby"])

    # ------------------------------------------------------------------
    # Model detection & feature probing
    # ------------------------------------------------------------------

    async def _detect_model(self):
        """Query projector identity and probe supported features. Runs once at startup."""
        try:
            url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576"
            response = requests.post(url, timeout=5)
            status = _parse_benq_json(response)[0]

            model = status.get('acProjectorName', 'Unknown')
            fw    = status.get('acProjectorFWVersion', 'Unknown')
            self.log(f"Model: {model} | Firmware: {fw}")

            self._feature_profile = await self._probe_features()
            self.log(f"Feature profile: {self._feature_profile}")

        except Exception as e:
            if "header" not in str(e).lower():
                self.log(f"Model detection skipped ({e}) — using defaults")

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
            r = requests.post(url, timeout=3)
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
            self.error(f"Feature '{feature_name}' failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll(self):
        """Bulk status poll — one HTTP call covers power, lamp hours, source."""
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576"
        try:
            response = requests.post(url, timeout=5)
            data = _parse_benq_json(response)[0]
            self._fail_count = 0
            await self._apply_bulk_status(data)
            await self.set_available()

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
            await self._on_poll_failure(str(e))

    async def _apply_bulk_status(self, data):
        power = data.get("nPowerStatus")

        # Power state
        if power == POWER_ON:
            await self.set_capability_value("onoff", True)
            await self.set_capability_value("power_state", "on")
        elif power == POWER_WARMING:
            await self.set_capability_value("onoff", True)
            await self.set_capability_value("power_state", "warming")
            self.homey.set_timeout(self._poll, 30 * 1000)   # re-poll in 30s
        elif power == POWER_COOLING:
            await self.set_capability_value("onoff", False)
            await self.set_capability_value("power_state", "cooling")
            self.homey.set_timeout(self._poll, 30 * 1000)   # re-poll in 30s
        else:
            await self.set_capability_value("onoff", False)
            await self.set_capability_value("power_state", "standby")

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

        # Input source + volume — only meaningful when fully on
        if power == POWER_ON:
            source_id = data.get("nPWSourceID")
            if source_id is not None:
                await self.set_capability_value("input_source", str(source_id))
            await self._poll_volume()

    async def _poll_volume(self):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:917516"
        try:
            response = requests.post(url, timeout=3)
            level = _parse_benq_json(response)[0]["value"]   # 0-10
            await self.set_capability_value("volume_set", level / 10)
        except Exception:
            pass   # non-critical; slider just won't update

    async def _on_poll_failure(self, reason):
        self._fail_count += 1
        self.error(f"Poll failed ({self._fail_count}): {reason}")
        if self._fail_count >= 3:
            await self.set_unavailable("Projector unreachable")

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
            requests.post(url, timeout=5)
            await self.set_capability_value("onoff", True)
            await self.set_capability_value("power_state", "warming")
            await self.set_available()
            self.log("Power ON sent — projector warming up")
        except requests.exceptions.Timeout:
            self.error("Power ON timed out")
            raise Exception("Projector did not respond")
        except Exception as e:
            if "header" in str(e).lower():
                await self.set_capability_value("onoff", True)
                await self.set_capability_value("power_state", "warming")
                await self.set_available()
                self.log("Power ON sent (header error ignored)")
            else:
                self.error(f"Power ON failed: {e}")
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
                requests.post(base + step, timeout=5)
                self.log(f"Step {i}/5 sent")
                if i < len(steps):
                    await asyncio.sleep(0.5)
            await self.set_capability_value("onoff", False)
            await self.set_capability_value("power_state", "cooling")
            self.log("Power OFF sequence complete — projector cooling")
        except Exception as e:
            if "header" in str(e).lower():
                await self.set_capability_value("onoff", False)
                await self.set_capability_value("power_state", "cooling")
                self.log("Power OFF sent (header error ignored)")
            else:
                self.error(f"Power OFF failed: {e}")
                raise

    # ------------------------------------------------------------------
    # Input source
    # ------------------------------------------------------------------

    async def _on_input_source(self, value, opts=None):
        """value is string source ID e.g. '5' for HDMI 1."""
        source_id = int(value)
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917504,v:{source_id}"
        try:
            requests.post(url, timeout=5)
            self.log(f"Input switched to source {source_id}")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error(f"Input switch failed: {e}")
                raise

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    async def _on_volume_set(self, value, opts=None):
        """value is 0.0-1.0 from Homey; projector expects 0-10."""
        level = round(value * 10)
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917516,v:{level}"
        try:
            requests.post(url, timeout=5)
            self.log(f"Volume set to {level}/10")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error(f"Volume set failed: {e}")

    async def _on_volume_mute(self, value, opts=None):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851980,v:12"
        try:
            requests.post(url, timeout=5)
            self.log(f"Mute {'on' if value else 'off'} (toggle sent)")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error(f"Mute toggle failed: {e}")


homey_export = BenQSH915Device

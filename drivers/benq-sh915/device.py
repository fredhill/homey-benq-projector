import asyncio
import requests
from homey.device import Device

POWER_ON      = 0
POWER_STANDBY = 6
POWER_WARMING = 7
POWER_COOLING = 8

LAMP_RATED_HOURS = {0: 3500, 1: 5000, 2: 5000, 3: 6000, 4: 5000}


class BenQSH915Device(Device):
    async def on_init(self):
        await super().on_init()
        self.log("BenQ SH915 device initialized")

        settings = self.get_settings()
        self._ip = settings.get("ip_address", "10.50.0.29")
        self._poll_interval = int(settings.get("poll_interval", 300))
        self._fail_count = 0

        self.register_capability_listener("onoff", self._on_onoff)
        self.register_capability_listener("input_source", self._on_input_source)
        self.register_capability_listener("volume_set", self._on_volume_set)
        self.register_capability_listener("volume_mute", self._on_volume_mute)

        self.homey.set_interval(self._poll, self._poll_interval * 1000)
        self.log(f"Polling every {self._poll_interval}s")

    async def on_settings(self, old_settings, new_settings, changed_keys):
        if "ip_address" in changed_keys:
            self._ip = new_settings["ip_address"]
        if "poll_interval" in changed_keys:
            self._poll_interval = int(new_settings["poll_interval"])

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll(self):
        """Bulk status poll — one call covers power, lamp hours, source."""
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576"
        try:
            response = requests.post(url, timeout=5)
            data = response.json()[0]
            self._fail_count = 0
            await self._apply_bulk_status(data)
            await self.set_available()

        except requests.exceptions.ConnectionError:
            await self._on_poll_failure("connection refused")
        except requests.exceptions.Timeout:
            await self._on_poll_failure("timeout")
        except Exception as e:
            if "header" in str(e).lower():
                return  # expected BenQ malformed header, not an error
            await self._on_poll_failure(str(e))

    async def _apply_bulk_status(self, data):
        power = data.get("nPowerStatus")

        # onoff + power_state
        if power == POWER_ON:
            await self.set_capability_value("onoff", True)
            await self.set_capability_value("power_state", "on")
        elif power == POWER_WARMING:
            await self.set_capability_value("onoff", True)
            await self.set_capability_value("power_state", "warming")
        elif power == POWER_COOLING:
            await self.set_capability_value("onoff", False)
            await self.set_capability_value("power_state", "cooling")
        else:
            await self.set_capability_value("onoff", False)
            await self.set_capability_value("power_state", "standby")

        # Lamp hours — readable in all states including standby
        lamp_hours = data.get("nLampHour")
        if lamp_hours is not None:
            await self.set_capability_value("lamp_hours", lamp_hours)
            lamp_mode = data.get("nLampMode", 0)
            rated = LAMP_RATED_HOURS.get(lamp_mode, 3500)
            pct = round(lamp_hours / rated * 100)
            self.log(f"Lamp: {lamp_hours}h / {rated}h rated ({pct}%)")
            if lamp_hours >= rated - 200:
                self.error(f"URGENT: lamp at {lamp_hours}h, replace soon!")
            elif lamp_hours >= rated - 500:
                self.log(f"WARNING: lamp reaching end of life at {lamp_hours}h")

        # Input source — only meaningful when projector is fully on
        if power == POWER_ON:
            source_id = data.get("nPWSourceID")
            if source_id is not None:
                await self.set_capability_value("input_source", str(source_id))

        # Volume — separate read, only when on
        if power == POWER_ON:
            await self._poll_volume()

    async def _poll_volume(self):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:917516"
        try:
            response = requests.post(url, timeout=3)
            level = response.json()[0]["value"]  # 0-10
            await self.set_capability_value("volume_set", level / 10)
        except Exception:
            pass  # non-critical; volume UI just won't update

    async def _on_poll_failure(self, reason):
        self._fail_count += 1
        self.error(f"Poll failed ({self._fail_count}): {reason}")
        if self._fail_count >= 3:
            await self.set_unavailable("Projector unreachable")

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------

    async def _on_onoff(self, value, opts):
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
        base = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf"
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
            self.log("Power OFF sequence completed — projector cooling")
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

    async def _on_input_source(self, value, opts):
        """value is string source ID e.g. '5' for HDMI 1"""
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

    async def _on_volume_set(self, value, opts):
        """value is 0.0-1.0 from Homey; projector expects 0-10"""
        level = round(value * 10)
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917516,v:{level}"
        try:
            requests.post(url, timeout=5)
            self.log(f"Volume set to {level}/10")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error(f"Volume set failed: {e}")

    async def _on_volume_mute(self, value, opts):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851980,v:12"
        try:
            requests.post(url, timeout=5)
            self.log(f"Mute {'on' if value else 'off'} (toggle sent)")
        except Exception as e:
            if "header" not in str(e).lower():
                self.error(f"Mute toggle failed: {e}")


homey_export = BenQSH915Device

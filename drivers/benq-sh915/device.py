import asyncio
import requests
from homey.device import Device


class BenQSH915Device(Device):
    async def on_init(self):
        await super().on_init()
        self.log("BenQ SH915 device initialized")

        settings = self.get_settings()
        self._ip = settings.get("ip_address", "10.50.0.29")
        self._poll_interval = int(settings.get("poll_interval", 300))
        self._fail_count = 0

        self.register_capability_listener("onoff", self._on_onoff)

        # set_interval fires immediately, so no separate startup check needed
        self.homey.set_interval(self._check_status, self._poll_interval * 1000)
        self.log(f"Polling every {self._poll_interval}s")

    async def on_settings(self, old_settings, new_settings, changed_keys):
        if "ip_address" in changed_keys:
            self._ip = new_settings["ip_address"]
        if "poll_interval" in changed_keys:
            self._poll_interval = int(new_settings["poll_interval"])

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
            await self.set_available()
            self.log("Power ON command sent successfully")
        except requests.exceptions.Timeout:
            self.error("Power ON timed out")
            raise Exception("Projector did not respond")
        except Exception as e:
            if "header" in str(e).lower():
                await self.set_capability_value("onoff", True)
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
                    await asyncio.sleep(0.5)  # non-blocking delay
            await self.set_capability_value("onoff", False)
            self.log("Power OFF sequence completed")
        except Exception as e:
            if "header" in str(e).lower():
                await self.set_capability_value("onoff", False)
                self.log("Power OFF sent (header error ignored)")
            else:
                self.error(f"Power OFF failed: {e}")
                raise

    async def _check_status(self):
        url = f"http://{self._ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:851982"
        try:
            response = requests.post(url, timeout=3)
            data = response.json()
            value = data[0]["value"]
            self._fail_count = 0
            if value == 0:
                await self.set_capability_value("onoff", True)
                self.log("Status check: ON")
            elif value == 6:
                await self.set_capability_value("onoff", False)
                self.log("Status check: OFF")
            elif value == 8:
                await self.set_capability_value("onoff", False)
                self.log("Status check: COOLING")
            await self.set_available()
        except Exception as e:
            self._fail_count += 1
            self.error(f"Status check failed ({self._fail_count}): {e}")
            # Mark unavailable after 3 consecutive failures
            if self._fail_count >= 3:
                await self.set_unavailable("Projector unreachable")


homey_export = BenQSH915Device

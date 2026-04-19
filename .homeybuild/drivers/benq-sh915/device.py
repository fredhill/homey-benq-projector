"""BenQ SH915 Projector Device"""
import time
import requests
from homey import HomeyDevice


class BenQSH915Device(HomeyDevice):
    """BenQ SH915 Projector Device"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ip_address = None
        self.poll_interval = 300
        self.poll_timer = None

    async def on_init(self):
        """Device initialized"""
        self.log("BenQ SH915 device initialized")

        settings = self.get_settings()
        self.ip_address = settings.get('ip_address', '10.50.0.220')
        self.poll_interval = settings.get('poll_interval', 300)

        self.register_capability_listener('onoff', self.on_capability_onoff)

        await self.start_polling()
        await self.check_status()

    async def on_uninit(self):
        """Device removed"""
        self.log("BenQ SH915 device removed")
        if self.poll_timer:
            self.homey.clear_interval(self.poll_timer)

    async def on_settings_changed(self, old_settings, new_settings, changed_keys):
        """Settings changed"""
        if 'ip_address' in changed_keys:
            self.ip_address = new_settings['ip_address']
            self.log(f"IP address updated to: {self.ip_address}")

        if 'poll_interval' in changed_keys:
            self.poll_interval = new_settings['poll_interval']
            await self.start_polling()

    async def on_capability_onoff(self, value):
        """On/off capability changed"""
        if value:
            return await self.turn_on()
        else:
            return await self.turn_off()

    async def turn_on(self):
        """Turn projector on"""
        url = f"http://{self.ip_address}/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851977,v:9"

        try:
            self.log("Sending power ON command")
            requests.post(url, timeout=5)
            await self.set_capability_value('onoff', True)
            self.log("Power ON command sent successfully")
            return True

        except requests.exceptions.Timeout:
            self.error("Power ON command timed out")
            raise Exception("Projector did not respond")
        except Exception as e:
            # BenQ returns malformed headers — treat header errors as success
            if "header" in str(e).lower():
                await self.set_capability_value('onoff', True)
                self.log("Power ON sent (header error ignored)")
                return True
            self.error(f"Power ON failed: {e}")
            raise

    async def turn_off(self):
        """Turn projector off via 5-step sequence"""
        base_url = f"http://{self.ip_address}/cgi-bin/webctrl.cgi.elf"

        sequence = [
            "?&t:26,c:6,p:851982",
            "?&t:26,c:5,p:851977,v:9",
            "?&t:26,c:6,p:851982",
            "?&t:26,c:5,p:851977,v:9",
            "?&t:26,c:6,p:1012",
        ]

        try:
            self.log("Sending power OFF sequence (5 steps)")

            for i, step in enumerate(sequence, 1):
                requests.post(base_url + step, timeout=5)
                self.log(f"Step {i}/5 sent")
                if i < len(sequence):
                    time.sleep(0.5)

            await self.set_capability_value('onoff', False)
            self.log("Power OFF sequence completed")
            return True

        except Exception as e:
            if "header" in str(e).lower():
                await self.set_capability_value('onoff', False)
                self.log("Power OFF sent (header error ignored)")
                return True
            self.error(f"Power OFF failed: {e}")
            raise

    async def check_status(self):
        """Check current projector status"""
        url = f"http://{self.ip_address}/cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:851982"

        try:
            response = requests.post(url, timeout=3)
            data = response.json()
            value = data[0]['value']

            if value == 0:
                await self.set_capability_value('onoff', True)
                self.log("Status check: ON")
            elif value == 6:
                await self.set_capability_value('onoff', False)
                self.log("Status check: OFF")
            elif value == 8:
                await self.set_capability_value('onoff', False)
                self.log("Status check: COOLING")

            await self.set_available()

        except Exception as e:
            self.error(f"Status check failed: {e}")

    async def start_polling(self):
        """Start status polling"""
        if self.poll_timer:
            self.homey.clear_interval(self.poll_timer)

        self.poll_timer = self.homey.set_interval(
            self.check_status,
            self.poll_interval * 1000
        )
        self.log(f"Status polling started (every {self.poll_interval} seconds)")

"""BenQ SH915 Projector Driver"""
from homey import HomeyDriver


class BenQSH915Driver(HomeyDriver):
    """BenQ SH915 Projector Driver"""

    async def on_init(self):
        """Driver initialized"""
        self.log("BenQ SH915 driver initialized")

    async def on_pair(self, session):
        """Handle pairing"""

        async def list_devices_handler(data):
            return [
                {
                    "name": "BenQ SH915 Projector",
                    "data": {
                        "id": "benq-sh915"
                    },
                    "settings": {
                        "ip_address": "10.50.0.220",
                        "poll_interval": 300
                    }
                }
            ]

        session.set_handler("list_devices", list_devices_handler)

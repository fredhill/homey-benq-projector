from homey.driver import Driver, ListDeviceProperties


class BenQSH915Driver(Driver):
    async def on_init(self):
        await super().on_init()
        self.log("BenQ SH915 driver initialized")

    async def on_pair_list_devices(self, view_data):
        device: ListDeviceProperties = {
            "name": "BenQ SH915 Projector",
            "data": {"id": "benq-sh915"},
            "settings": {
                "ip_address": "10.50.0.29",
                "poll_interval": 300,
            },
        }
        return [device]


homey_export = BenQSH915Driver

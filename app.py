from homey.app import App


class BenQSH915App(App):
    async def on_init(self):
        await super().on_init()
        self.log("BenQ SH915 app initialized")


homey_export = BenQSH915App

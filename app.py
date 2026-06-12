from homey.app import App


class BenQSH915App(App):
    async def on_init(self):
        await super().on_init()
        self.log("BenQ SH915 app initialized")
        self._register_flow_cards()

    # ------------------------------------------------------------------
    # Flow cards — action & condition run listeners.
    # Triggers are fired from the device itself (see device.py).
    # The device is always provided to the listener as args["device"].
    # ------------------------------------------------------------------

    def _register_flow_cards(self):
        flow = self.homey.flow

        # Actions
        flow.get_action_card("set_input_source").register_run_listener(self._action_set_input_source)
        flow.get_action_card("set_picture_mode").register_run_listener(self._action_set_picture_mode)
        flow.get_action_card("set_eco_blank").register_run_listener(self._action_set_eco_blank)

        # Conditions
        flow.get_condition_card("input_source_is").register_run_listener(self._condition_input_source_is)
        flow.get_condition_card("power_state_is").register_run_listener(self._condition_power_state_is)
        flow.get_condition_card("picture_mode_is").register_run_listener(self._condition_picture_mode_is)

        self.log("Flow cards registered")

    # ---- Actions ----

    async def _action_set_input_source(self, args, **state):
        await args["device"].flow_set_input_source(args["source"])

    async def _action_set_picture_mode(self, args, **state):
        await args["device"].flow_set_picture_mode(args["mode"])

    async def _action_set_eco_blank(self, args, **state):
        await args["device"].flow_set_eco_blank(args["state"] == "on")

    # ---- Conditions ----

    async def _condition_input_source_is(self, args, **state):
        return args["device"].get_capability_value("input_source") == args["source"]

    async def _condition_power_state_is(self, args, **state):
        return args["device"].get_capability_value("power_state") == args["state"]

    async def _condition_picture_mode_is(self, args, **state):
        return args["device"].get_capability_value("picture_mode") == args["mode"]


homey_export = BenQSH915App

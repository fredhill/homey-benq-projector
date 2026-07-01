import asyncio

from homey.app import App

# SDK-internal functions whose detached-task exceptions we want to swallow.
# set_unavailable / set_available schedule their real work as background
# asyncio tasks; if that task raises (observed on several Homey firmwares),
# the exception surfaces as an uncatchable "Task exception was never
# retrieved" crash. A try/except around the call cannot reach it — only the
# event loop's exception handler can.
_SDK_AVAILABILITY_FUNCS = frozenset({
    "set_unavailable_function",
    "set_available_function",
})


def _is_sdk_availability_error(exc):
    """True if the exception's traceback passes through an SDK availability task."""
    tb = getattr(exc, "__traceback__", None)
    while tb is not None:
        if tb.tb_frame.f_code.co_name in _SDK_AVAILABILITY_FUNCS:
            return True
        tb = tb.tb_next
    return False


class BenQSH915App(App):
    async def on_init(self):
        await super().on_init()
        self.log("BenQ SH915 app initialized")
        self._install_exception_guard()
        self._register_flow_cards()

    # ------------------------------------------------------------------
    # Swallow uncatchable detached-task exceptions from the SDK's
    # availability functions, while passing everything else through to the
    # normal handler so real errors are still reported.
    # ------------------------------------------------------------------

    def _install_exception_guard(self):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        previous = loop.get_exception_handler()

        def handler(loop, context):
            exc = context.get("exception")
            if exc is not None and _is_sdk_availability_error(exc):
                self.log("Suppressed SDK availability task exception (set_(un)available)")
                return
            if previous is not None:
                previous(loop, context)
            else:
                loop.default_exception_handler(context)

        loop.set_exception_handler(handler)
        self.log("Installed asyncio exception guard")

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

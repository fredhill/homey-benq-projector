"""BenQ SH915 Projector App"""
from homey import Homey


class BenQSH915App(Homey):
    """BenQ SH915 Projector App"""

    async def on_init(self):
        """App initialized"""
        self.log("BenQ SH915 app initialized")

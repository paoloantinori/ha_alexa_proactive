"""Config flow for Alexa Proactive Events."""

from homeassistant import config_entries

from .const import DOMAIN


class AlexaProactiveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Alexa Proactive Events."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        pass

    async def async_step_setup(self, user_input=None):
        """Handle the SMAPI setup step."""
        pass

    async def async_step_finish(self, user_input=None):
        """Handle the finish step."""
        pass
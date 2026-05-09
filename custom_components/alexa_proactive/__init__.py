"""The Alexa Proactive Events integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Alexa Proactive Events component from YAML (not used)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Alexa Proactive Events from a config entry."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Alexa Proactive Events config entry."""
    entries = hass.data.get(DOMAIN)
    if entries is not None:
        entries.pop(entry.entry_id, None)
        if not entries:
            hass.data.pop(DOMAIN, None)
    return True
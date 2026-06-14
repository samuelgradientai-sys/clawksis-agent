"""Xiaomi MiMo provider profile."""

from providers import register_provider
from providers.base import ProviderProfile

xiaomi = ProviderProfile(
    name="xiaomi",
    aliases=("mimo", "xiaomi-mimo"),
    env_vars=("XIAOMI_API_KEY",),
    base_url="https://api.xiaomimimo.com/v1",
    supports_health_check=False,  # /v1/models returns 401 even with valid key
    # mimo-v2-omni is vision-capable — vision routing is handled at the model
    # level (models.dev catalog / _PROVIDER_VISION_MODELS), not on the profile.
)

register_provider(xiaomi)

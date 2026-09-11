"""The composition root of ELA: where the configuration is read and the pieces are wired.

The only package that names concrete implementations (architecture rule 27, ADR 0023 §12):
everything else in ``src/ela`` receives a port. It is also the first directory of ``src/ela``
that spec §48 does not list, and ADR 0023 §1 says why — what it holds belongs to no existing
package, because a module that knows about all of them cannot live inside one of them.
"""

from ela.composition.errors import ConfigurationError
from ela.composition.root import ELA_ACTOR, Ela, build
from ela.composition.settings import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_ORPHAN_AFTER_SECONDS,
    MIN_TOKEN_LENGTH,
    ApiSettings,
    CoreSettings,
    Settings,
)
from ela.composition.system import SystemClock, UuidGenerator

__all__ = [
    "DEFAULT_API_HOST",
    "DEFAULT_API_PORT",
    "DEFAULT_ORPHAN_AFTER_SECONDS",
    "ELA_ACTOR",
    "MIN_TOKEN_LENGTH",
    "ApiSettings",
    "ConfigurationError",
    "CoreSettings",
    "Ela",
    "Settings",
    "SystemClock",
    "UuidGenerator",
    "build",
]

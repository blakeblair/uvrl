from dataclasses import dataclass
from pathlib import Path

# -------------------------
# Data model
# -------------------------

@dataclass
class DiscoveredApp:
    name: str
    path: Path

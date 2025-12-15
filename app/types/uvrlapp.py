from dataclasses import dataclass

# -------------------------
# Data model
# -------------------------

@dataclass
class DiscoveredApp:
    name: str
    path: Path

from dataclasses import dataclass
from pathlib import Path


@dataclass
class uvrl_config:
    app_list_config_path: Path

    def __init__(self):
        # TODO: Properly read configs
        self.app_list_config_path = Path("./assets/config/applist.json")


import time
from enum import Enum


class SensorState(Enum):
    CLEAR = 0     # beam unbroken / HMD not present
    BLOCKED = 1   # beam broken / HMD present


class SensorStub:
    def __init__(self):
        self.state = SensorState.CLEAR

    def read(self) -> SensorState:
        return self.state

    def toggle(self):
        # manual toggle for testing
        self.state = (
            SensorState.BLOCKED
            if self.state == SensorState.CLEAR
            else SensorState.CLEAR
        )

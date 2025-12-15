from app.sensors import SensorState
from app.utils.enums import VRState



class StateMachine:
    def __init__(self):
        self.vr_state = VRState.OUTSIDE_VR
        self._last_sensor_state: SensorState | None = None

    def update(self, sensor_state: SensorState):
        if self._last_sensor_state is None:
            self._last_sensor_state = sensor_state
            return

        if sensor_state != self._last_sensor_state:
            self._handle_transition(self._last_sensor_state, sensor_state)
            self._last_sensor_state = sensor_state

    def _handle_transition(self, prev: SensorState, curr: SensorState):
        if prev == SensorState.CLEAR and curr == SensorState.BLOCKED:
            self.vr_state = VRState.INSIDE_VR
            print("Transition: HMD DOCKED → UNDOCKED")

        elif prev == SensorState.BLOCKED and curr == SensorState.CLEAR:
            self.vr_state = VRState.OUTSIDE_VR
            print("Transition: HMD UNDOCKED → DOCKED")

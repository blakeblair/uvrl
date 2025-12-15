from enum import Enum

class VRState(Enum):
    OUTSIDE_VR = 0,
    INSIDE_VR = 1,
    ENTERING_VR = 2,
    EXITING_VR = 3

import time
from app.sensor import SensorStub
from app.state import StateMachine
from app.os import get_os
from app.discovery import discover_apps

apps = discover_apps()
print("Discovered apps:")
for app in apps:
    print(f"- {app.name} @ {app.path} ({app.source})")

from app.steam_discovery import find_installed_steam_apps, steam_apps_to_discovered

steam_apps = find_installed_steam_apps()
discovered = steam_apps_to_discovered(steam_apps)

print("Steam-discovered apps:")
for app in discovered:
    print(f"- {app.name} [{app.confidence}] {app.path}")

from app.steam_discovery import find_steam_libraries
print("Steam libraries:")
for lib in find_steam_libraries():
    print("-", lib)


def main():
    sensor = SensorStub()
    state_machine = StateMachine()

    print("Press ENTER to toggle sensor state. Ctrl+C to exit.")
    print("Detected OS:", get_os().value)
    try:
        while True:
            input()
            sensor.toggle()
            current = sensor.read()
            state_machine.update(current)

    except KeyboardInterrupt:
        print("Exiting.")


if __name__ == "__main__":
    main()


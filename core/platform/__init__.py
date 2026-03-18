"""
HAL9000 — Cross-Platform API
Auto-detects OS and provides the right platform implementation.

Usage:
    from core.platform import platform
    platform.set_volume(50)
    platform.open_application("Safari")
    platform.screenshot()
"""

import platform as _platform

_os = _platform.system()

if _os == "Darwin":
    from core.platform.mac import MacPlatform
    platform = MacPlatform()
elif _os == "Windows":
    from core.platform.windows import WindowsPlatform
    platform = WindowsPlatform()
elif _os == "Linux":
    from core.platform.linux import LinuxPlatform
    platform = LinuxPlatform()
else:
    from core.platform.base import PlatformAPI
    platform = PlatformAPI()
    print(f"[HAL Platform] WARNING: Unsupported OS '{_os}'. System tools will not work.")

print(f"[HAL Platform] {platform.name} detected")

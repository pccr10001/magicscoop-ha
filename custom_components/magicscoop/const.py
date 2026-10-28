"""Constants for the MagicScoop integration."""
from __future__ import annotations

DOMAIN = "magicscoop"
MANUFACTURER = "MagicScoop"
DEFAULT_NAME = "MagicScoop"

# --- MQTT broker (hardcoded in app, mTLS client cert bundled) ---
BROKER_HOST = "cloud.gingerway.com"
BROKER_PORT = 8883
BROKER_USER = "MSAPP"
BROKER_PASS = "24HV56AKh"  # note the trailing 'h'
KEEPALIVE = 120

# --- config entry keys ---
CONF_EMAIL = "email"
CONF_EN_PASSWORD = "en_password"
CONF_CID = "cid"
CONF_DEVICES = "devices"  # list of {"dno": int, "name": str, "model": str, "version": str}

# device type that we import (cat litter box). Water fountains use another type.
DEVICE_TYPE_LITTER = 0

# --- topics ---
def topic_pub_cloud() -> str:
    return "MS/APP/TO_CLOUD"


def topic_pub_device(dno: int) -> str:
    return f"MS/APP/TO_MS/{dno}"


def topic_sub_cloud(cid: str) -> str:
    return f"MS/CLOUD/TO_APP/{cid}/#"


def topic_sub_device(dno: int) -> str:
    return f"MS/MS/TO_APP/{dno}/#"


# --- CMD names ---
CMD_FORGOT_PASSWORD = "CLOUD_FORGOT_PASSWORD"
CMD_GET_PASSWORD = "CLOUD_GET_PASSWORD"
CMD_LOGIN = "CLOUD_ACCOUNT_LOGIN"
CMD_ALL_MS = "CLOUD_ACCOUNT_ALL_MS"
CMD_CURRENT_STATUS = "MS_CURRENT_STATUS"
CMD_GET_SETTINGS = "MS_GET_SETTINGS"
CMD_UPDATE_SETTINGS = "MS_UPDATE_SETTINGS"
CMD_GET_DIAGNOSE = "MS_GET_DIAGNOSE"
CMD_PERFORM_ACTION = "MS_PERFORM_ACTION"
CMD_REMOTE_ACK = "REMOTE_ACK"

# --- MS_PERFORM_ACTION COMMAND values (verified against live traffic) ---
PERFORM_START_CLEAN = 12  # Remote Clean
PERFORM_RESET = 2  # Reset / return to standby
PERFORM_STERILIZE = 4  # Sterilize (M1 Pro)
PERFORM_PAUSE = 5  # Pause current operation

# --- enums: numeric value -> translation key ---
DEVICE_STATUS = {
    0: "starting",
    1: "aligning",
    2: "packing",
    3: "standby",
    4: "resetting",
    5: "occupied",
    6: "clumping",
    7: "auto_clean",
    8: "manual_clean",
    9: "periodic_clean",
    10: "remote_clean",
    11: "sterilizing",
    12: "replacing_trash_bag",
    13: "wifi_setting",
    14: "ota",
    15: "waste_full",
    16: "factory_test",
    17: "durability_test",
    18: "rotate_test",
    19: "ready",
}

DEVICE_SUB_STATUS = {
    0: "running",
    1: "finished",
    2: "paused",
    3: "occupied",
    4: "interrupted",
    5: "move_pinched",
    6: "rotate_pinched",
    7: "pinched",
    8: "timeout",
}

LITTER_VOLUME = {
    0: "unknown",
    1: "insufficient",
    2: "less",
    3: "appropriate",
    4: "sufficient",
    5: "full",
    6: "overload",
    7: "invalid",
}


# --- settings enums: device value -> option key ---
CLEAN_MODE = {0: "auto", 1: "manual", 2: "periodic"}
CLEAN_MODE_REV = {v: k for k, v in CLEAN_MODE.items()}

# ClumpingTime is stored as a bucket; 0/1 (1min/3min) were removed in fw 7.3
CLUMPING_TIME = {2: 5, 3: 10, 4: 20, 5: 40, 6: 60}  # value -> minutes
CLUMPING_TIME_REV = {v: k for k, v in CLUMPING_TIME.items()}

PERIODIC_MODE = {
    0: "off",
    1: "every_2h",
    2: "every_4h",
    3: "every_6h",
    4: "every_8h",
    5: "every_12h",
}
PERIODIC_MODE_REV = {v: k for k, v in PERIODIC_MODE.items()}

SLEEP_MODE = {0: "off", 1: "six", 2: "seven", 3: "eight", 4: "nine"}
SLEEP_MODE_REV = {v: k for k, v in SLEEP_MODE.items()}

# settings field -> options / value<->key maps
SELECT_SPECS = {
    "CleanMode": {
        "options": list(CLEAN_MODE.values()),
        "v2k": CLEAN_MODE,
        "k2v": CLEAN_MODE_REV,
    },
    # ClumpingTime option keys are the minutes as strings
    "ClumpingTime": {
        "options": ["5", "10", "20", "40", "60"],
        "v2k": {2: "5", 3: "10", 4: "20", 5: "40", 6: "60"},
        "k2v": {"5": 2, "10": 3, "20": 4, "40": 5, "60": 6},
    },
    "PeriodicMode": {
        "options": list(PERIODIC_MODE.values()),
        "v2k": PERIODIC_MODE,
        "k2v": PERIODIC_MODE_REV,
    },
    "SleepMode": {
        "options": list(SLEEP_MODE.values()),
        "v2k": SLEEP_MODE,
        "k2v": SLEEP_MODE_REV,
    },
}

SWITCH_FIELDS = [
    "CleanUVEnable",
    "TwiceDumping",
    "VibrateScooper",
    "DisableRearPIR",
    "StepMatCheck",
    "SleepCleanDisable",
    "SleepLightOpen",
    "SleepRingLightOff",
]

# MoveSensitivity / RotateSensitivity are intentionally NOT exposed:
# the mobile app has no UI for them.
NUMBER_FIELDS = {
    "PeriodicActionHour": (0, 23),
    "PeriodicActionMin": (0, 59),
    "PeriodicActionStopHour": (0, 23),
    "PeriodicActionStopMin": (0, 59),
    "SleepStartHour": (0, 23),
    "SleepStartMin": (0, 59),
}

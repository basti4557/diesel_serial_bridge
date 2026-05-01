import json
import logging
import signal
import sys
from time import sleep

import crcmod.predefined
import paho.mqtt.client as mqtt
from paho.mqtt.subscribeoptions import SubscribeOptions
import serial

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load options from Home Assistant supervisor
# ---------------------------------------------------------------------------
OPTIONS_FILE = "/data/options.json"

with open(OPTIONS_FILE) as f:
    options = json.load(f)

MQTT_BROKER = options["mqtt_broker"]
MQTT_PORT = int(options["mqtt_port"])
MQTT_USER = options.get("mqtt_user", "")
MQTT_PASSWORD = options.get("mqtt_password", "")
SERIAL_PORT = options["serial_port"]
SERIAL_BAUD = int(options["serial_baud"])

# ---------------------------------------------------------------------------
# Heater state
# ---------------------------------------------------------------------------
heater_mode_val = -1
heater_temp_val = -1
ventilation_val = -1
power_level_val = -1

# ---------------------------------------------------------------------------
# Serial / MQTT helpers
# ---------------------------------------------------------------------------


def finish_message(packet: bytearray) -> bytearray:
    """Wrap *packet* with the 0x72 start byte and append a Modbus CRC."""
    crcfunc = crcmod.predefined.mkCrcFun("modbus")
    crc = crcfunc(bytes(packet))
    new_packet = bytearray()
    new_packet.append(0x72)
    new_packet.extend(packet)
    # high byte first, then low byte
    new_packet.append((crc >> 8) & 0xFF)
    new_packet.append(crc & 0xFF)
    return new_packet


def _build_packet(
    command_byte: int, mode: int, temp: int, vent: int, power: int
) -> bytearray:
    packet = bytearray()
    packet.append(0xAA)  # start
    packet.append(0x03)  # from controller
    packet.append(0x06)  # 6 bytes in message
    packet.append(0x00)  # blank
    packet.append(command_byte)  # 0x01 = turn on, 0x02 = get/set
    packet.append(0xFF)  # unused
    packet.append(0xFF)  # unused
    packet.append(mode)
    packet.append(temp)
    packet.append(vent)
    packet.append(power)
    return packet


def _send_raw(message: bytearray) -> None:
    for byte in message:
        log.debug("TX: %s", hex(byte))
    for _ in range(2):
        ser.write(message)
        sleep(0.4)
        ser.flushInput()


def power_on(mode: int, temp: int, vent: int, power: int) -> None:
    log.info(
        "Sending power-on command (mode=%d temp=%d vent=%d power=%d)",
        mode,
        temp,
        vent,
        power,
    )
    _send_raw(finish_message(_build_packet(0x01, mode, temp, vent, power)))


def send_command(mode: int, temp: int, vent: int, power: int) -> None:
    log.info(
        "Sending set command (mode=%d temp=%d vent=%d power=%d)",
        mode,
        temp,
        vent,
        power,
    )
    _send_raw(finish_message(_build_packet(0x02, mode, temp, vent, power)))


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to MQTT broker %s:%d", MQTT_BROKER, MQTT_PORT)
    else:
        log.error("MQTT connection failed with code %d", rc)


def on_message(client, userdata, msg):
    global heater_mode_val, heater_temp_val, ventilation_val, power_level_val

    log.info("MQTT RX [%s]: %s", msg.topic, msg.payload)

    if msg.topic == "van/diesel/control":
        if msg.payload == b"On":
            log.info("Sending heat command")
            power_on(heater_mode_val, heater_temp_val, ventilation_val, power_level_val)
        elif msg.payload == b"Off":
            log.info("Sending off command")
            ser.write(b"F")

    elif msg.topic == "van/diesel/setpoint_heater_temp":
        heater_temp_val = int(msg.payload)
        send_command(heater_mode_val, heater_temp_val, ventilation_val, power_level_val)

    elif msg.topic == "van/diesel/setpoint_power_level":
        power_level_val = int(msg.payload)
        send_command(heater_mode_val, heater_temp_val, ventilation_val, power_level_val)

    elif msg.topic == "van/diesel/setpoint_heater_mode_string":
        mode_map = {b"Power": 4, b"Panel": 2, b"Heater": 1}
        if msg.payload in mode_map:
            heater_mode_val = mode_map[msg.payload]
            send_command(
                heater_mode_val, heater_temp_val, ventilation_val, power_level_val
            )

    elif msg.topic == "van/diesel/setpoint_ventilation":
        ventilation_val = int(msg.payload)
        send_command(heater_mode_val, heater_temp_val, ventilation_val, power_level_val)


# ---------------------------------------------------------------------------
# Serial parsing
# ---------------------------------------------------------------------------


def parse_and_submit(serial_data: bytes, ident_string: str, index: int, topic: str):
    """Find *ident_string* in the hex-dump, parse the field at *index*, publish."""
    line = str(serial_data)
    pos = line.find(ident_string)
    if pos == -1:
        return None

    parts = line[pos:].split(" ")
    if len(parts) <= index:
        return None  # message truncated / split across reads

    raw = parts[index]
    # Strip leading '0x' / '0X' prefix and any preceding garbage bytes
    # The dump format is "0X..." (occasionally "0XFFFFFF..." when byte is sign-extended)
    if len(raw) < 5:  # e.g. "0X0" or "0XFF"
        raw = raw[2:]
    else:  # e.g. "0XFFFFFF3C" – keep only last byte
        raw = raw[-2:]

    try:
        value = int(raw, 16)
        client.publish(topic, value)
        return value
    except ValueError:
        client.publish(topic + "_debug", "parse_error:" + raw)
        return None


# Identifier strings for the serial protocol
HEATER_TEMP_CONT_STR = "C >> 0XFFFFFFAA 0X3 0X1 0X0 0X11 0X"
HEATER_TEMP_CONT_IDX = 7

HEATER_TEMP_HEAT_STR = "H >> 0XFFFFFFAA 0X4 0X1 0X0 0X11 0X"
HEATER_TEMP_HEAT_IDX = 7

HEATER_STATE_STR = "H >> 0XFFFFFFAA 0X4 0X13 0X0 0XF"
HEATER_STATE_IDX = 16
HEATER_VOLTAGE_IDX = 13
HEATER_CORETEMP_IDX = 15
HEATER_FANSPD_IDX = 18
HEATER_FANSPD2_IDX = 19
HEATER_FUEL_IDX = 21
HEATER_FUEL2_IDX = 23
HEATER_GLOW_IDX = 24

SETPOINT_STR = "H >> 0XFFFFFFAA 0X4 0X6 0X0 0X"
SETPOINT_UNKNOWN_IDX = 7
SETPOINT_UNKNOWN2_IDX = 8
SETPOINT_MODE_IDX = 9
SETPOINT_TEMP_IDX = 10
SETPOINT_VENT_IDX = 11
SETPOINT_POWER_IDX = 12

HEATER_STATE_MAP = {
    0: ("off", "OFF"),
    1: ("starting", "ON"),
    4: ("heating", "ON"),
    5: ("clearing-shutting-down", "OFF"),
    6: ("heating-idle", "ON"),
}

HEATER_MODE_MAP = {
    1: "Heater",
    2: "Panel",
    4: "Power",
}


def check_temperature() -> None:
    global heater_mode_val, heater_temp_val, ventilation_val, power_level_val

    raw = ser.read(ser.inWaiting())

    parse_and_submit(
        raw,
        HEATER_TEMP_CONT_STR,
        HEATER_TEMP_CONT_IDX,
        "van/diesel/temperature_controller",
    )
    parse_and_submit(
        raw, HEATER_TEMP_HEAT_STR, HEATER_TEMP_HEAT_IDX, "van/diesel/temperature_heater"
    )

    parse_and_submit(
        raw, HEATER_STATE_STR, HEATER_STATE_IDX, "van/diesel/heater_state_n"
    )
    parse_and_submit(
        raw, HEATER_STATE_STR, HEATER_VOLTAGE_IDX, "van/diesel/heater_voltage"
    )
    parse_and_submit(
        raw, HEATER_STATE_STR, HEATER_CORETEMP_IDX, "van/diesel/heater_coretemp"
    )
    parse_and_submit(
        raw, HEATER_STATE_STR, HEATER_FANSPD_IDX, "van/diesel/heater_fanspd"
    )
    parse_and_submit(
        raw, HEATER_STATE_STR, HEATER_FANSPD2_IDX, "van/diesel/heater_fanspd2"
    )
    parse_and_submit(raw, HEATER_STATE_STR, HEATER_FUEL_IDX, "van/diesel/heater_fuel")
    parse_and_submit(raw, HEATER_STATE_STR, HEATER_FUEL2_IDX, "van/diesel/heater_fuel2")
    parse_and_submit(raw, HEATER_STATE_STR, HEATER_GLOW_IDX, "van/diesel/heater_glow")

    # Publish human-readable heater state
    line = str(raw)
    pos = line.find(HEATER_STATE_STR)
    if pos != -1:
        data = line[pos:]
        if len(data) > 130:
            parts = data.split(" ")
            try:
                state_val = int(parts[HEATER_STATE_IDX][2:], 16)
                if state_val in HEATER_STATE_MAP:
                    state_str, simple = HEATER_STATE_MAP[state_val]
                    client.publish("van/diesel/heater_state", state_str)
                    client.publish("van/diesel/heater_state_simple", simple)
            except (ValueError, IndexError):
                pass

    # Setpoints
    heater_mode_val = parse_and_submit(
        raw, SETPOINT_STR, SETPOINT_MODE_IDX, "van/diesel/setpoint_heater_mode"
    )
    if heater_mode_val in HEATER_MODE_MAP:
        client.publish(
            "van/diesel/setpoint_heater_mode_string", HEATER_MODE_MAP[heater_mode_val]
        )

    heater_temp_val = parse_and_submit(
        raw, SETPOINT_STR, SETPOINT_TEMP_IDX, "van/diesel/setpoint_heater_temp"
    )
    ventilation_val = parse_and_submit(
        raw, SETPOINT_STR, SETPOINT_VENT_IDX, "van/diesel/setpoint_ventilation"
    )
    power_level_val = parse_and_submit(
        raw, SETPOINT_STR, SETPOINT_POWER_IDX, "van/diesel/setpoint_power_level"
    )
    parse_and_submit(
        raw, SETPOINT_STR, SETPOINT_UNKNOWN_IDX, "van/diesel/setpoint_unknown"
    )
    parse_and_submit(
        raw, SETPOINT_STR, SETPOINT_UNKNOWN2_IDX, "van/diesel/setpoint_unknown2"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def shutdown(signum, frame):
    log.info("Shutting down…")
    try:
        client.disconnect()
    except Exception:
        pass
    try:
        ser.close()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

log.info("Opening serial port %s @ %d baud", SERIAL_PORT, SERIAL_BAUD)
ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD)

log.info("Connecting to MQTT broker %s:%d", MQTT_BROKER, MQTT_PORT)
client = mqtt.Client(client_id="VAN-DIESEL")
client.on_connect = on_connect
client.on_message = on_message

if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

client.connect(MQTT_BROKER, MQTT_PORT)

subscribe_opts = SubscribeOptions(qos=1, noLocal=True)
client.subscribe("van/diesel/control")
client.subscribe("van/diesel/setpoint_power_level", options=subscribe_opts)
client.subscribe("van/diesel/setpoint_heater_temp", options=subscribe_opts)
client.subscribe("van/diesel/setpoint_ventilation", options=subscribe_opts)
client.subscribe("van/diesel/setpoint_heater_mode_string", options=subscribe_opts)

log.info("Starting main loop")
while True:
    if ser.inWaiting() > 500:
        check_temperature()
    client.loop()

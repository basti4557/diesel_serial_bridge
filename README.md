# Diesel Heater Serial Bridge Add-on

Home Assistant Supervisor add-on that bridges a diesel heater serial interface to MQTT topics under `van/diesel/*`.

## Installation

1. Add this repository URL to Home Assistant as a custom add-on repository.
2. Install the `Diesel Heater Serial Bridge` add-on.
3. Configure MQTT broker and serial port options.
4. Start the add-on.

## Options

- `mqtt_broker`: MQTT broker hostname or IP address.
- `mqtt_port`: MQTT broker port.
- `mqtt_user`: MQTT username (optional).
- `mqtt_password`: MQTT password (optional).
- `serial_port`: Serial device path (for example `/dev/ttyUSB0`).
- `serial_baud`: Serial baud rate.

## Notes

- The add-on requires access to a serial device and should run in a Supervisor environment.
- For MQTT, `core-mosquitto` is used by default but you can point to any reachable broker.

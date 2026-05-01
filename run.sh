#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Diesel Heater Serial Bridge…"
exec python3 /diesel_bridge.py

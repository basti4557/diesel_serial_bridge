ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python, pip and bash
RUN apk add --no-cache python3 py3-pip bash

# Install Python dependencies with --break-system-packages flag
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /requirements.txt

# Copy application files
COPY diesel_bridge.py /diesel_bridge.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Set the entrypoint
CMD ["/run.sh"]

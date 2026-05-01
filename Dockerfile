ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python, pip and bash
RUN apk add --no-cache python3 py3-pip bash

# Remove the externally-managed-environment restriction
RUN rm /usr/lib/python*/EXTERNALLY-MANAGED 2>/dev/null || true

# Upgrade pip
RUN pip3 install --upgrade pip

# Install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt

# Copy application files
COPY diesel_bridge.py /diesel_bridge.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

# Set the entrypoint
CMD ["/run.sh"]

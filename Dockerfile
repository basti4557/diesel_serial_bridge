ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip bash

# Install bashio for Home Assistant compatibility
RUN apk add --no-cache curl && \
    mkdir -p /usr/local/lib/bashio && \
    curl -L https://github.com/hassio-addons/bashio/archive/master.tar.gz | tar xz -C /usr/local/lib/bashio --strip-components 1 && \
    ln -s /usr/local/lib/bashio/lib /usr/lib/bashio && \
    ln -s /usr/local/lib/bashio/bin/bashio.sh /usr/bin/bashio

COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt

COPY diesel_bridge.py /diesel_bridge.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]

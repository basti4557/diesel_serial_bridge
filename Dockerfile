ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt

COPY diesel_bridge.py /diesel_bridge.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]

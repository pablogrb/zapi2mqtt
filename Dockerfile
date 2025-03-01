FROM python:3.11

# Set the working directory
WORKDIR /zapi2mqtt

# Copy the necessary files
COPY zapi2mqtt.py .
COPY sensors.py .
# Copy the config files
COPY config/* /zapi2mqtt/config/

# Update pip and install required dependencies using a different package index mirror
RUN pip install paho-mqtt pyyaml requests

# Command to run the script
CMD ["python", "zapi2mqtt.py"]

# build with:
# docker build --network=host -t zapi2mqtt:latest /home/pablogrb/docker_dev/zapi2mqtt

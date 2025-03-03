# zapi2mqtt
This project is designed to pull data from the Zephyr API and send it to an MQTT broker. It utilizes a Python script (`zapi2mqtt.py`) that interacts with sensors defined in a configuration file.

## Project Structure
```
zapi2mqtt/
├─ .github/
│  ├─ workflows/
│  │  ├─ docker-publish.yml
├─ config/
│  ├─ creds.yml
│  ├─ sensors.yml
├── README.md
├── sensors.yml
└── zapi2mqtt.py
```

## Requirements
- Python 3.x
- Required Python packages are specified in the `Dockerfile`.

## Configuration Files
- **creds.yml**: Contains the credentials for connecting to the MQTT broker.
- **sensors.yml**: Defines the configuration for the sensors, including their types and settings.

## Docker Setup

### Image

The image can be pulled from the [ghcr.io/pablogrb/zapi2mqtt:latest](ghcr.io/pablogrb/zapi2mqtt:latest)

### Binds

A local folder with your version of the configuration files is required to run the container. The default configuration provided is for reference purposes only.

### Example docker run
Run from the folder where you stored your version of the configuration files.
```
docker run --name zapi2mqtt -v "$(pwd)$":/zapi2mqtt/config ghcr.io/pablogrb/zapi2mqtt:latest
```
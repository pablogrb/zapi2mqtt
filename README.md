# zapi2mqtt
This project is designed to pull data from the Zephyr API and send it to an MQTT broker. It utilizes a Python script (`zapi2mqtt.py`) that interacts with sensors defined in a configuration file.

## Project Structure
```
zapi2mqtt
├── Dockerfile
├── zapi2mqtt.py
├── sensors.py
├── creds.yml
├── sensors.yml
└── README.md
```

## Requirements
- Python 3.x
- Required Python packages are specified in the `Dockerfile`.

## Configuration Files
- **creds.yml**: Contains the credentials for connecting to the MQTT broker.
- **sensors.yml**: Defines the configuration for the sensors, including their types and settings.

## Docker Setup
To run the project using Docker, ensure you have Docker installed on your machine. The `Dockerfile` is set up to allow access to the YAML configuration files from a bind-mounted folder.

### Building the Docker Image
Navigate to the directory where the image will be created and run the following command to build the Docker image:
```
docker build --network=host -t zapi2mqtt:latest /home/pablogrb/docker_dev/zapi2mqtt
```

### Running the Docker Container
To run the Docker container with access to the configuration files, use the following command:
```
docker run -v /path/to/your/config:/zapi2mqtt zapi2mqtt
```
Replace `/path/to/your/config` with the path to the directory containing your `creds.yml` and `sensors.yml` files.

## Usage
Once the container is running, the script will continuously pull data from the Zephyr API and publish it to the specified MQTT broker. Ensure that the MQTT broker is accessible and properly configured in the `creds.yml` file.

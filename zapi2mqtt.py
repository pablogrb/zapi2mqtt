'''Pulls data from the Zephyr API and sends it to an MQTT broker'''

# Imports
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from random import randint

import yaml
from paho.mqtt import client as mqtt

from sensors import ZephyrSensor

def zapi2mqtt_sync(userdata, client):
    '''Sync the sensor data from the Zephyr API to the MQTT broker'''
    minutes = 5
    # loop forever
    while True:
    # for i in range(2):
        if not client.is_connected():
            print("Waiting for MQTT connection")
            sleep(minutes * 60)
            continue
        # start an excec timer
        s_t = datetime.now(timezone.utc)
        # print(f"Hi from sync #{i}")

        # update the sensor data
        for _, s_dc in userdata['sensors'].items():
            if s_dc['type'] == 'Zephyr':
                # update the sensor data
                s_dc['sensor'].update()
                # publish the sensor data
                s_dc['sensor'].publish(client)

        # calculate the time to sleep
        e_t = datetime.now(timezone.utc)
        sleep((minutes * 60) - (e_t - s_t).total_seconds())

def on_connect(client, userdata, flags, rc, properties):
    '''Callback function for when the client connects to the broker'''
    # check if the connection was successful
    if rc != 0:
        raise ConnectionError(f"Connection failed with result code {rc}")
    print("Connected to MQTT Broker!")
    # send the Home Assistant discovery messages
    for _, s_dc in userdata['sensors'].items():
        if s_dc['type'] == 'Zephyr' and s_dc['hass_discovery'] is True:
            s_dc['sensor'].hass_discovery(client)

def zapi2mqtt():
    '''Main function to pull data from the Zephyr API and send it to an MQTT broker'''
    # detect if running in docker
    if Path("/.dockerenv").exists():
        basepath = Path("/zapi2mqtt")
        print("Running in Docker")
        # list the contents of the basepath
        print(list(basepath.iterdir()))
    else:
        basepath = Path(__file__).parent
    
    # load the config file
    with open(Path(f"{basepath}/config/creds.yml"), "r", encoding="utf-8") as in_file:
        creds = yaml.safe_load(in_file)
        print(f"{basepath}/config/creds.yml")
        print(creds)
    
    # load the sensors
    with open(Path(f"{basepath}/config/sensors.yml"), "r", encoding='utf-8') as in_file:
        sensors = yaml.safe_load(in_file)
        print(f"{basepath}/config/sensors.yml")
        print(sensors)

    # package the config data into the userdata variable
    userdata = {
        'creds': creds,
        'sensors': sensors
    }

    # Initialize the sensors
    print("Initializing sensors")
    for znum, s_dc in userdata['sensors'].items():
        if s_dc['type'] == 'Zephyr':
            # Initialize the Zephyr sensor
            s_dc['sensor'] = ZephyrSensor(znum, userdata)
            # Update the sensor data
            s_dc['sensor'].update()

    # Setup the mqtt client
    print("Setting up MQTT client")
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata=userdata
    )
    client.on_connect = on_connect
    # connect to the mqtt broker using username / password authentication
    print("Connecting to MQTT broker")
    client.username_pw_set(
        creds['MQTT']['username'], creds['MQTT']['password']
    )
    client.connect(creds['MQTT']['host'], creds['MQTT']['port'])
    client.loop_start()

    zapi2mqtt_sync(userdata, client)
    
    # Disconnect from the MQTT broker
    client.loop_stop()
    client.disconnect()

# entry point
if __name__ == "__main__":

    zapi2mqtt()

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
    # loop forever
    # while True
    for i in range(5):
        if not client.is_connected():
            print("Waiting for MQTT connection")
            sleep(60)
            continue
        # start an excec timer
        s_t = datetime.now(timezone.utc)
        print(f"Hi from sync #{i}")

        # placeholder for the update and publish loop
        sleep(randint(0, 60))

        # calculate the time to sleep
        e_t = datetime.now(timezone.utc)
        sleep(60 - (e_t - s_t).total_seconds())

def on_connect(client, userdata, flags, rc, properties):
    '''Callback function for when the client connects to the broker'''
    # check if the connection was successful
    if rc != 0:
        raise ConnectionError(f"Connection failed with result code {rc}")
    print("Connected to MQTT Broker!")

def zapi2mqtt():
    '''Main function to pull data from the Zephyr API and send it to an MQTT broker'''
    # load the config file
    with open(Path("creds.yml"), "r", encoding="utf-8") as in_file:
        creds = yaml.safe_load(in_file)
    
    # load the sensors
    with open(Path('sensors.yml'), "r", encoding='utf-8') as in_file:
        sensors = yaml.safe_load(in_file)

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

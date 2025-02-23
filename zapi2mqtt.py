'''Pulls data from the Zephyr API and sends it to an MQTT broker'''

# Imports
import json
from datetime import datetime, timedelta, timezone
from time import sleep

import requests
import yaml
from pathlib import Path
from paho.mqtt import client as mqtt

def zfetch_interval(interval, dt_obj, username, userkey, slot, znumber):
    '''Fetches the lastest 15 minute averaged data for a slot in a zephyr unit'''
    # get the closest 15 minute interval to the datetime
    # get the current datetime in UTC
    now = dt_obj
    # round down to the nearest quarter hour
    end_dt = now - timedelta(
        minutes=now.minute % 15, seconds=now.second, microseconds=now.microsecond
    )
    # subtract 'interval' minutes
    str_dt = end_dt - timedelta(minutes=interval)

    # ## HACK: displace 15 minutes back to avoid missing data
    # str_dt = str_dt - timedelta(minutes=15)
    # end_dt = end_dt - timedelta(minutes=15)

    # set the averaging chain id
    # the following averaging strings are available:
    # 0 (No averaging)
    # 1 (Hourly)
    # 2 (Daily starting at midnight)
    # 3 (15 minute averaging)
    # 6 (returns 15mins, 1hr, 8hr and 1 day averages)
    # 7 (returns 15mins and 1hr averages)
    # 8 (returns 8hr averages)
    # 9 (3 minute averaging)
    # 14 (1 minute averaging)
    # 15 (5 minute averaging)
    avg_id = "3"

    # set the base url
    base_url = "https://data.earthsense.co.uk/measurementdata/v1"

    # build the request url
    req_url = (base_url + "/" + str(znumber) + "/" +
               str_dt.strftime("%Y%m%d%H%M") + "/" + end_dt.strftime("%Y%m%d%H%M") + "/" +
               slot + "/" + avg_id)

    # set the headers
    req_headers = {
        'accept': "application/json",
        'username': username,
        'userkey': userkey
    }

    # HACK: try the api 5 times to deal with random 401 unauthorized errors
    tries=5
    for req_try in range(tries):
        # pull the zephyr data from the api
        with requests.get(url=req_url, headers=req_headers, timeout=180) as url:
            # Check if API request was successful
            if url.status_code == 200:
                zephyr_dict = json.loads(url.text)
                print(f"Retrieved zephyr data for user {username}")
                break
            if url.status_code == 401:
                print(f"API responded 401, trying again (attempt = {req_try})")
                sleep(15)
                continue
            raise ValueError(f'API returned: {url.text}')
    else:
        raise RuntimeError(f'API failed to respond OK after {tries} tries')

    return zephyr_dict

def zapi2mqtt_sync():
    '''Load the API data and send to the MQTT broker'''
    # load the config file
    with open(Path("creds.yml"), "r", encoding="utf-8") as in_file:
        creds = yaml.safe_load(in_file)
    
        # load the sensors
    with open(Path('sensors.yml'), "r", encoding='utf-8') as in_file:
        sensors = yaml.safe_load(in_file)

    # loop through the sensors
    for _, s_dc in sensors['sensors'].items():
        if s_dc['type'] == 'Zephyr':
            # get the zephyr info
            zid = s_dc['znumber']
            zsl = s_dc['slot']

            # get the current datetime in UTC
            dt_obj = datetime.now(timezone.utc)

            # fetch the data from the zephyr api
            zephyr_data = zfetch_interval(
                interval=15,
                dt_obj=dt_obj,
                username=creds['ZAPI']['username'],
                userkey=creds['ZAPI']['password'],
                slot=zsl,
                znumber=zid,
            )
            
            # dump the data to a yaml file
            with open(Path("zephyr_data.yml"), "w", encoding="utf-8") as out_file:
                yaml.dump(zephyr_data, out_file, default_flow_style=False)
        break

def on_connect(client, userdata, flags, rc, properties):
    '''Callback function for when the client connects to the broker'''
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect, return code: {rc}")

def zapi2mqtt():
    '''Main function to pull data from the Zephyr API and send it to an MQTT broker'''
    # load the config file
    with open(Path("creds.yml"), "r", encoding="utf-8") as in_file:
        creds = yaml.safe_load(in_file)
    
    # load the sensors
    with open(Path('sensors.yml'), "r", encoding='utf-8') as in_file:
        sensors = yaml.safe_load(in_file)

    # Setup the mqtt client
    print("Setting up MQTT client")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect    
    # connect to the mqtt broker using username / password authentication
    print("Connecting to MQTT broker")
    client.username_pw_set(
        creds['MQTT']['username'], creds['MQTT']['password']
    )
    client.connect(creds['MQTT']['host'], creds['MQTT']['port'])
    client.loop_start()

    # wait for the client to connect
    sleep(60)

# entry point
if __name__ == "__main__":

    zapi2mqtt()

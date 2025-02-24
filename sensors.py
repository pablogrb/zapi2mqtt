'''Class definition for the zapi sensors'''
# imports
import json
from datetime import datetime, timedelta, timezone
from time import sleep

import requests

# Location object
class SensorLocation():
    '''Class definition for a sensor location'''
    def __init__(self):
        '''Initialize the sensor location'''
        self.loc_override = False
        self.latitude = None
        self.longitude = None
    
    def update(self, latitude, longitude):
        '''Update the sensor location'''
        self.latitude = latitude
        self.longitude = longitude 

# EarthSense Zephyr
class ZephyrSensor():
    '''Class definition for an EarthSense Zephyr sensor'''
    def __init__(self, znum, userdata):
        '''Initialize the Zephyr sensor'''
        print(f"Initializing Zephyr sensor {znum}")
        # Zephyr Number and slot
        self.znum = znum
        self.slot = userdata['sensors'][znum]['slot']
        self.skey = f"slot{userdata['sensors'][znum]['slot']}"
        # MQTT topic
        self.topic = f"zapi2mqtt/zephyr/{znum}"
        # Credentials
        self.username = userdata['creds']['ZAPI']['username']
        self.password = userdata['creds']['ZAPI']['password']
        # Zephyr Location
        self.loc = SensorLocation()
        if ('latitude' in userdata['sensors'][znum]) and ('longitude' in userdata['sensors'][znum]):
            self.loc.loc_override = True
            self.loc.update(userdata['sensors'][znum]['latitude'], userdata['sensors'][znum]['longitude'])
        else:
            self.loc_override = False
        # Zephyr measurements
        self.meas = {}
        self.meas['NO'] = {'apiname': 'NO', 'data': None}
        self.meas['NO2'] = {'apiname': 'NO2', 'data': None}
        self.meas['O3'] = {'apiname': 'O3', 'data': None}
        self.meas['PM1'] = {'apiname': 'particulatePM1', 'data': None}
        self.meas['PM25'] = {'apiname': 'particulatePM25', 'data': None}
        self.meas['PM10'] = {'apiname': 'particulatePM10', 'data': None}
    
    def update(self):
        '''Update the sensor data from the API'''
        # get the closest 15 minute interval to the datetime
        # get the current datetime in UTC
        now = datetime.now(timezone.utc)
        # round down to the nearest quarter hour
        interval = 5
        end_dt = now - timedelta(
            minutes=now.minute % 5, seconds=now.second, microseconds=now.microsecond
        )
        # subtract 'interval' minutes
        str_dt = end_dt - timedelta(minutes=interval)

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
        avg_id = "15"

        # set the base url
        base_url = "https://data.earthsense.co.uk/measurementdata/v1"

        # build the request url
        req_url = (base_url + "/" + str(self.znum) + "/" +
                    str_dt.strftime("%Y%m%d%H%M") + "/" + end_dt.strftime("%Y%m%d%H%M") + "/" +
                    self.slot + "/" + avg_id)

        # set the headers
        req_headers = {
            'accept': "application/json",
            'username': self.username,
            'userkey': self.password
        }

        # HACK: try the api 5 times to deal with random 401 unauthorized errors
        tries=5
        for req_try in range(tries):
            # pull the zephyr data from the api
            with requests.get(url=req_url, headers=req_headers, timeout=180) as url:
                # Check if API request was successful
                if url.status_code == 200:
                    zephyr_dict = json.loads(url.text)
                    print(f"Retrieved zephyr data for {self.znum}")
                    break
                if url.status_code == 401:
                    print(f"API responded 401, trying again (attempt = {req_try})")
                    sleep(15)
                    continue
                raise ValueError(f'API returned: {url.text}')
        else:
            raise RuntimeError(f'API failed to respond OK after {tries} tries')
        
        # Parse the dictionary into the sensor data
        if avg_id == "3":
            avg_key = '15 min average on the quarter hours'
        elif avg_id == "15":
            avg_key = '5 minute averaging on the hour'
        if not self.loc.loc_override:
            self.loc.update(zephyr_dict['data'][avg_key]['head']['latitude']['data'][0],
                            zephyr_dict['data'][avg_key]['head']['longitude']['data'][0])
        for meas, mdic in self.meas.items():
            mdic['data'] = zephyr_dict['data'][avg_key][self.skey][mdic['apiname']]['data'][0]

    def publish(self, client):
        '''Publish the sensor data to the MQTT broker'''
        for meas, mdic in self.meas.items():
            client.publish(self.topic + "/" + meas, mdic['data'])
        client.publish(self.topic + "/latitude", self.loc.latitude)
        client.publish(self.topic + "/longitude", self.loc.longitude)
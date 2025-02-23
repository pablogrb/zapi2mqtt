'''Class definition for the zapi sensors'''
# imports
import json
from datetime import datetime, timedelta, timezone
from time import sleep

import requests

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
        if ('latitude' in userdata['sensors'][znum]) and ('longitude' in userdata['sensors'][znum]):
            self.loc_override = True
            self.latitude = userdata['sensors'][znum]['latitude']
            self.longitude = userdata['sensors'][znum]['longitude']
        else:
            self.loc_override = False
        # Zephyr measurements
        self.no = None
        self.no2 = None
        self.o3 = None
        self.pm1 = None
        self.pm25 = None
        self.pm10 = None
    
    def update(self):
        '''Update the sensor data from the API'''
        # get the closest 15 minute interval to the datetime
        # get the current datetime in UTC
        now = datetime.now(timezone.utc)
        # round down to the nearest quarter hour
        interval = 15
        end_dt = now - timedelta(
            minutes=now.minute % 15, seconds=now.second, microseconds=now.microsecond
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
        avg_id = "3"

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
        self.no = zephyr_dict['data']['15 min average on the quarter hours'][self.skey]['NO']['data'][0]
        self.no2 = zephyr_dict['data']['15 min average on the quarter hours'][self.skey]['NO2']['data'][0]
        self.o3 = zephyr_dict['data']['15 min average on the quarter hours'][self.skey]['O3']['data'][0]
        self.pm1 = zephyr_dict['data']['15 min average on the quarter hours'][self.skey]['particulatePM1']['data'][0]
        self.pm25 = zephyr_dict['data']['15 min average on the quarter hours'][self.skey]['particulatePM25']['data'][0]
        self.pm10 = zephyr_dict['data']['15 min average on the quarter hours'][self.skey]['particulatePM10']['data'][0]

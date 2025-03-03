'''Class definition for the zapi sensors'''
# imports
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from time import sleep

import requests

# Set up logging
logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
# pylint: disable=logging-fstring-interpolation

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
        logger.info(f"Initializing Zephyr sensor {znum}")
        # Zephyr Number and slot
        self.znum = znum
        self.slot = userdata['sensors'][znum]['slot']
        self.skey = f"slot{userdata['sensors'][znum]['slot']}"
        # Credentials
        self.username = userdata['creds']['ZAPI']['username']
        self.password = userdata['creds']['ZAPI']['password']
        # Check if the sensor is available and retrieve the model and firmware
        self.available = self.zinfo()
        if not self.available:
            try:
                raise ValueError(f"Zephyr {znum} is not available for user {self.username}")
            except ValueError as e:
                logger.error(e)
                sys.exit(1)
        # Zephyr Location
        self.loc = SensorLocation()
        if ('latitude' in userdata['sensors'][znum]) and ('longitude' in userdata['sensors'][znum]):
            self.loc.loc_override = True
            self.loc.update(userdata['sensors'][znum]['latitude'], userdata['sensors'][znum]['longitude'])
        else:
            self.loc_override = False
        # Zephyr measurements
        self.meas = {}
        self.meas['NO'] = {'apiname': 'NO', 'data': None, 'unit': 'µg/m³', 'd_class': 'nitrogen_monoxide'}
        self.meas['NO2'] = {'apiname': 'NO2', 'data': None, 'unit': 'µg/m³', 'd_class': 'nitrogen_dioxide'}
        self.meas['O3'] = {'apiname': 'O3', 'data': None, 'unit': 'µg/m³', 'd_class': 'ozone'}
        self.meas['PM1'] = {'apiname': 'particulatePM1', 'data': None, 'unit': 'µg/m³', 'd_class': 'pm1'}
        self.meas['PM25'] = {'apiname': 'particulatePM25', 'data': None, 'unit': 'µg/m³', 'd_class': 'pm25'}
        self.meas['PM10'] = {'apiname': 'particulatePM10', 'data': None, 'unit': 'µg/m³', 'd_class': 'pm10'}
        # AQI
        self.aqi = "No Data"
        # MQTT topic
        self.topic = f"zapi2mqtt/zephyr/{znum}"

    def zinfo(self):
        '''Return the Zephyr sensor information'''
        url = f"https://data.earthsense.co.uk/getzephyrs/{self.username}/{self.password}"
        # pull the zephyr data from the api
        with requests.get(url=url, timeout=180) as url:
            # Check if API request was successful
            if url.status_code == 200:
                zephyr_list = json.loads(url.text)
                logger.info(f"Retrieved zephyr data for user {self.username}")
            else:
                try:
                    raise ValueError(f'API returned: {url.text}')
                except ValueError as e:
                    logger.error(e)
                    sys.exit(1)

        # Check if the Zephyr is available
        for zephyr in zephyr_list:
            if zephyr['zNumber'] == self.znum:
                self.model = zephyr['serialNumber'][0:3]
                self.firmware = zephyr['firmwareVersion']
                return True
        return False

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
                    logger.info(f"Retrieved zephyr data for {self.znum}")
                    break
                if url.status_code == 401:
                    logger.warning(f"API responded 401, trying again (attempt = {req_try})")
                    sleep(15)
                    continue
                try:
                    raise ValueError(f'API returned: {url.text}')
                except ValueError as e:
                    logger.error(e)
                    sys.exit(1)
        else:
            try:
                raise RuntimeError(f'API failed to respond OK after {tries} tries')
            except RuntimeError as e:
                logger.error(e)
            return

        # Parse the dictionary into the sensor data
        avg_key = ''
        if avg_id == "3":
            avg_key = '15 min average on the quarter hours'
        elif avg_id == "15":
            avg_key = '5 minute averaging on the hour'
        if not self.loc.loc_override:
            self.loc.update(zephyr_dict['data'][avg_key]['head']['latitude']['data'][0],
                            zephyr_dict['data'][avg_key]['head']['longitude']['data'][0])
        for _, mdic in self.meas.items():
            mdic['data'] = zephyr_dict['data'][avg_key][self.skey][mdic['apiname']]['data'][0]

        # Calculate the AQI
        self.aqi = self.calc_aqi()

    def calc_aqi(self):
        '''Calcualte the European Air Quality Index'''
        # AQI breakpoints
        aqi_breaks = {
            'PM25': [10, 20, 25, 50, 75],
            'PM10': [20, 40, 50, 100, 150],
            'NO2': [40, 90, 120, 230, 340],
            'O3': [50, 100, 130, 240, 380],
            'SO2': [100, 200, 350, 500, 750],
        }
        # AQI categories
        # aqi_cats = ['Good', 'Fair', 'Moderate', 'Poor', 'Very Poor', 'Extremely Poor']
        # Calculate the AQI for each pollutant
        aqi_list = []
        for meas, mdic in self.meas.items():
            if mdic['data'] is not None and meas in aqi_breaks:
                for i, aqi_break in enumerate(aqi_breaks[meas]):
                    if mdic['data'] <= aqi_break:
                        aqi_list.append(i)
                        break

        # return aqi_cats[max(aqi_list)]
        return max(aqi_list)

    def publish(self, client):
        '''Publish the sensor data to the MQTT broker'''
        for meas, mdic in self.meas.items():
            client.publish(self.topic + "/" + meas, mdic['data'])
        # client.publish(self.topic + "/latitude", self.loc.latitude)
        # client.publish(self.topic + "/longitude", self.loc.longitude)
        client.publish(self.topic + "/aqi", self.aqi)
        # build the location attributes json
        loc_attr = {
            "latitude": self.loc.latitude,
            "longitude": self.loc.longitude
        }
        client.publish(self.topic + "/attributes", json.dumps(loc_attr))

    def hass_discovery(self, client):
        '''Publish the Home Assistant discovery message for every sensor'''
        logger.info(f"Publishing Home Assistant discovery messages for Zephyr {self.znum}")
        # concentration sensor discovery
        for meas in self.meas:
            # build the discovery message
            dis_msg = self.hass_sensor(meas)
            dis_msg['device'] = self.hass_device()
            # publish the discovery message
            client.publish(f"homeassistant/sensor/z{str(self.znum)}_{meas}/config", json.dumps(dis_msg), retain=True)
        # aqi sensor discovery
        # build the discovery message
        dis_msg = self.hass_sensor("aqi")
        dis_msg['device'] = self.hass_device()
        dis_msg['json_attributes_topic'] = self.topic + "/attributes"
        # publish the discovery message
        client.publish(f"homeassistant/sensor/z{self.znum}_aqi/config", json.dumps(dis_msg), retain=True)

    def hass_sensor(self, meas):
        '''Build the Home Assistant sensor discovery message'''
        dis_msg = {
            "name": f"Zephyr {self.znum} {meas}",
            "unique_id": f"z{self.znum}_{meas}",
            "object_id": f"z{self.znum}_{meas}",
            "qos": "0",
            "force_update": "true",
            "state_topic": self.topic + "/" + meas,
        }
        if meas == "aqi":
            dis_msg['device_class'] = "aqi"
            return dis_msg
        dis_msg['state_class'] = "measurement"
        dis_msg['unit_of_measurement'] = self.meas[meas]['unit']
        dis_msg['device_class'] = self.meas[meas]['d_class']
        return dis_msg

    def hass_device(self):
        '''Build the Home Assistant device discovery message'''
        return {
            "identifiers": [f"Z{self.znum}"],
            "name": "Zephyr",
            "manufacturer": "EarthSense",
            "model": self.model,
            "sw_version": self.firmware
        }

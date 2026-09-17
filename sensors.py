"""Class definition for the zapi sensors"""

# imports
import dataclasses
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from time import sleep

import requests
from requests.auth import HTTPBasicAuth

# Set up logging
logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# Dataclasses
@dataclasses.dataclass
class SensorLocation:
    """Class definition for a sensor location"""

    loc_override: bool = False
    latitude: float | None = None
    longitude: float | None = None


@dataclasses.dataclass
class ZephyrMeasurement:
    """Class definition for a Zephyr measurement"""

    name: str
    apiname: str
    unit: str
    device_class: str
    data: float | None = None


# EarthSense Zephyr
class ZephyrSensor:
    """Class definition for an EarthSense Zephyr sensor"""

    def __init__(self, znum, userdata):
        """Initialize the Zephyr sensor"""
        logger.info("Initializing Zephyr sensor %s", znum)
        # Zephyr Number and slot
        self.znum = znum
        self.slot = userdata["sensors"][znum]["slot"]
        self.skey = f"slot{userdata['sensors'][znum]['slot']}"
        # Credentials
        self.username = userdata["creds"]["ZAPI"]["username"]
        self.password = userdata["creds"]["ZAPI"]["password"]
        # Bearer token is valid for 7 days according to the Auth API docs
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        # Check if the sensor is available and retrieve the model and firmware
        self.available = self.zinfo()
        if not self.available:
            try:
                raise ValueError(
                    f"Zephyr {znum} is not available for user {self.username}"
                )
            except ValueError as exc:
                logger.error(exc)
                sys.exit(1)
        # Zephyr Location
        if ("latitude" in userdata["sensors"][znum]) and (
            "longitude" in userdata["sensors"][znum]
        ):
            self.loc = SensorLocation(
                loc_override=True,
                latitude=userdata["sensors"][znum]["latitude"],
                longitude=userdata["sensors"][znum]["longitude"],
            )
        else:
            self.loc = SensorLocation()
        # Zephyr measurements
        self.meas = [
            ZephyrMeasurement("NO", "NO", "µg/m³", "nitrogen_monoxide", None),
            ZephyrMeasurement("NO2", "NO2", "µg/m³", "nitrogen_dioxide", None),
            ZephyrMeasurement("O3", "O3", "µg/m³", "ozone", None),
            ZephyrMeasurement("PM1", "particulatePM1", "µg/m³", "pm1", None),
            ZephyrMeasurement("PM25", "particulatePM25", "µg/m³", "pm25", None),
            ZephyrMeasurement("PM10", "particulatePM10", "µg/m³", "pm10", None),
            ZephyrMeasurement("aqi", "", "", "aqi", None),
        ]
        # AQI
        self.aqi = "No Data"
        # MQTT topic
        self.topic = f"zapi2mqtt/zephyr/{znum}"

    def _get_token(self, force_refresh=False):
        """Return a valid bearer token from the EarthSense Auth API."""
        now = datetime.now(timezone.utc)
        if (
            not force_refresh
            and self._token is not None
            and self._token_expiry is not None
            and now < self._token_expiry
        ):
            return self._token

        auth_url = "https://service.earthsense.co.uk/auth/api/AuthUser"
        with requests.get(
            auth_url,
            auth=HTTPBasicAuth(self.username, self.password),
            timeout=180,
        ) as response:
            if response.status_code != 200:
                try:
                    raise ValueError(f"Auth API returned {response.status_code}: {response.text}")
                except ValueError as exc:
                    logger.error(exc)
                    sys.exit(1)

            try:
                token_payload = response.json()
            except ValueError:
                token_payload = response.text

        token = None
        if isinstance(token_payload, dict):
            for key in ("token", "access_token", "jwt", "bearer", "authToken"):
                if key in token_payload and isinstance(token_payload[key], str):
                    token = token_payload[key]
                    break
            if token is None:
                for value in token_payload.values():
                    if isinstance(value, str) and value.count(".") == 2:
                        token = value
                        break
        elif isinstance(token_payload, str) and token_payload:
            token = token_payload.strip()

        if not token:
            try:
                raise ValueError("Could not parse bearer token from Auth API response")
            except ValueError as exc:
                logger.error(exc)
                sys.exit(1)

        self._token = token
        self._token_expiry = now + timedelta(days=7) - timedelta(minutes=5)
        return self._token

    def _auth_headers(self):
        """Build authenticated request headers for Zephyr API calls."""
        token = self._get_token()
        return {
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def zinfo(self):
        """Return the Zephyr sensor information"""
        url = "https://service.earthsense.co.uk/zephyr/api/zephyr"
        headers = self._auth_headers()
        # pull the zephyr data from the api
        zephyr_list = None
        for _ in range(2):
            with requests.get(url=url, headers=headers, timeout=180) as response:
                if response.status_code == 200:
                    zephyr_list = response.json()
                    logger.info("Retrieved zephyr data for user %s", self.username)
                    break

                if response.status_code == 401:
                    headers = {
                        "accept": "application/json",
                        "Authorization": (
                            f"Bearer {self._get_token(force_refresh=True)}"
                        ),
                    }
                    continue

                try:
                    raise ValueError(
                        f"API returned {response.status_code}: {response.text}"
                    )
                except ValueError as exc:
                    logger.error(exc)
                    sys.exit(1)

        if zephyr_list is None:
            logger.error("Unable to retrieve zephyr list after token refresh")
            sys.exit(1)

        # Check if the Zephyr is available
        for zephyr in zephyr_list:
            if zephyr["znumber"] == int(self.znum):
                self.model = zephyr["serialNumber"][0:3]
                self.firmware = zephyr["firmwareVersion"]
                return True
        return False

    def update(self):
        """Update the sensor data from the API"""
        # get the closest 5 minute interval to the datetime
        # get the current datetime in UTC
        now = datetime.now(timezone.utc)
        # round down to the nearest 5 minute boundary
        interval = 5
        end_dt = now - timedelta(
            minutes=now.minute % 5, seconds=now.second, microseconds=now.microsecond
        )
        # subtract interval minutes
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

        # build the request for v3 endpoint
        req_url = f"https://service.earthsense.co.uk/zephyr/api/zephyr/{int(self.znum)}/data"
        req_params = {
            "start_date": str_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "averaging": int(avg_id),
            "slots": self.slot,
        }
        req_headers = self._auth_headers()

        # HACK: try the api 5 times to deal with random 401 unauthorized errors
        tries = 5
        for req_try in range(tries):
            # catch connection errors in cases of slow dns
            try:
                # pull the zephyr data from the api
                with requests.get(
                    url=req_url,
                    params=req_params,
                    headers=req_headers,
                    timeout=180,
                ) as response:
                    # Check if API request was successful
                    if response.status_code == 200:
                        zephyr_dict = response.json()
                        logger.info("Retrieved zephyr data for %s", self.znum)
                        break
                    # no data available
                    if response.status_code == 240:
                        logger.warning("No data available for %s", self.znum)
                        return False
                    # retry on 401 unauthorized, 429 rate limit, or 500 server error
                    if response.status_code in (401, 429, 500):
                        if response.status_code == 401:
                            req_headers = {
                                "accept": "application/json",
                                "Authorization": (
                                    f"Bearer {self._get_token(force_refresh=True)}"
                                ),
                            }
                        logger.warning(
                            "API responded %i, trying again (attempt = %s)",
                            response.status_code,
                            req_try,
                        )
                        sleep(15)
                        continue
                    # raise an error and exit on any other status code
                    try:
                        raise ValueError(
                            f"API returned {response.status_code}: {response.text}"
                        )
                    except ValueError as exc:
                        logger.error(exc)
                        sys.exit(1)
            # catch connection errors
            except requests.exceptions.ConnectionError as exc:
                logger.warning("Connection error, trying again (attempt = %s)", req_try)
                logger.warning(exc)
                sleep(15)
                continue
        else:
            logger.warning("API failed to respond OK after %s tries", tries)
            return False

        # Parse the v3 data structure into the sensor data
        data_groups = zephyr_dict.get("data", {}).get("data", [])
        if not data_groups:
            logger.warning("No measurement series returned for %s", self.znum)
            return False

        series = data_groups[0].get("data", [])
        series_values = {}
        for item in series:
            if "species" not in item:
                continue
            latest = None
            for value in reversed(item.get("data", [])):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    latest = float(value)
                    break
            series_values[item["species"]] = latest

        # Keep location in sync with server-reported values unless overridden
        if not self.loc.loc_override:
            self.loc.latitude = series_values.get("latitude")
            self.loc.longitude = series_values.get("longitude")

        species_aliases = {
            "NO": ["NO"],
            "NO2": ["NO2"],
            "O3": ["O3"],
            "PM1": ["PM1", "particulatePM1"],
            "PM25": ["PM2p5", "PM25", "particulatePM25"],
            "PM10": ["PM10", "particulatePM10"],
        }
        for meas in self.meas:
            if meas.name == "aqi":
                continue
            meas.data = None
            for species in species_aliases.get(meas.name, [meas.apiname]):
                if species in series_values:
                    meas.data = series_values[species]
                    break

        # Calculate the AQI
        self.aqi = self.calc_aqi()

        return True

    def calc_aqi(self):
        """Calcualte the European Air Quality Index"""
        # AQI breakpoints
        aqi_breaks = {
            "PM25": [5, 15, 50, 90, 140],
            "PM10": [15, 45, 120, 195, 270],
            "NO2": [10, 25, 60, 100, 150],
            "O3": [60, 100, 120, 160, 180],
            "SO2": [20, 40, 125, 190, 275],
        }
        # AQI categories
        # aqi_cats = ['Good', 'Fair', 'Moderate', 'Poor', 'Very Poor', 'Extremely Poor']
        # Calculate the AQI for each pollutant
        aqi_list = []
        for meas in self.meas:
            if meas.data is not None and meas.name in aqi_breaks:
                for i, aqi_break in enumerate(aqi_breaks[meas.name]):
                    if meas.data <= aqi_break:
                        aqi_list.append(i)
                        break

        if not aqi_list:
            return "No Data"

        # return aqi_cats[max(aqi_list)]
        return max(aqi_list)

    def publish(self, client):
        """Publish the sensor data to the MQTT broker"""
        for meas in self.meas:
            client.publish(self.topic + "/" + meas.name, meas.data)
        client.publish(self.topic + "/aqi", self.aqi)
        # build the location attributes json
        loc_attr = {"latitude": self.loc.latitude, "longitude": self.loc.longitude}
        client.publish(self.topic + "/attributes", json.dumps(loc_attr))

    def hass_discovery(self, client):
        """Publish the Home Assistant discovery message for every sensor"""
        logger.info(
            "Publishing Home Assistant discovery messages for Zephyr %s", self.znum
        )
        # concentration sensor discovery
        for meas in self.meas:
            # build the discovery message
            dis_msg = self.hass_sensor(meas)
            dis_msg["device"] = self.hass_device()
            if meas.name == "aqi":
                dis_msg["json_attributes_topic"] = self.topic + "/attributes"
            # publish the discovery message
            client.publish(
                f"homeassistant/sensor/z{self.znum}_{meas.name}/config",
                json.dumps(dis_msg),
                retain=True,
            )

    def hass_sensor(self, meas):
        """Build the Home Assistant sensor discovery message"""
        dis_msg: dict[str, object]
        dis_msg = {
            "name": f"Zephyr {self.znum} {meas.name}",
            "unique_id": f"z{self.znum}_{meas.name}",
            "default_entity_id": f"z{self.znum}_{meas.name}",
            "qos": "0",
            "force_update": "true",
        }
        if meas.name == "aqi":
            dis_msg["state_topic"] = self.topic + "/aqi"
            dis_msg["device_class"] = "aqi"
            return dis_msg

        dis_msg["state_topic"] = self.topic + "/" + meas.name
        dis_msg["state_class"] = "measurement"
        dis_msg["unit_of_measurement"] = meas.unit
        dis_msg["device_class"] = meas.device_class
        return dis_msg

    def hass_device(self):
        """Build the Home Assistant device discovery message"""
        return {
            "identifiers": [f"Z{self.znum}"],
            "name": "Zephyr",
            "manufacturer": "EarthSense",
            "model": self.model,
            "sw_version": self.firmware,
        }

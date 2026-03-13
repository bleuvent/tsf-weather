from flask import Flask, request, Response
import requests
from datetime import datetime, timedelta
import os
import traceback
import time
import random
import re

app = Flask(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

WEATHERAPI_KEY = os.environ.get("WEATHERAPI_KEY", "")
WEATHERAPI_URL = "http://api.weatherapi.com/v1/forecast.json"

USE_WEATHERAPI = bool(WEATHERAPI_KEY)

weather_cache = {}
CACHE_DURATION = timedelta(minutes=30)
LAST_REQUEST_TIME = 0
MIN_REQUEST_INTERVAL = 0.5 if USE_WEATHERAPI else 2.0

def get_cache_key(lat, lon):
    return f"{round(lat, 1)}_{round(lon, 1)}"

def get_cached_weather(lat, lon):
    key = get_cache_key(lat, lon)
    if key in weather_cache:
        data, timestamp = weather_cache[key]
        age = datetime.now() - timestamp
        if age < CACHE_DURATION:
            return data
    return None

def set_cached_weather(lat, lon, data):
    key = get_cache_key(lat, lon)
    weather_cache[key] = (data, datetime.now())

def c_to_f(c):
    return (c * 9/5) + 32

def rate_limit():
    global LAST_REQUEST_TIME
    elapsed = time.time() - LAST_REQUEST_TIME
    if elapsed < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - elapsed + random.uniform(0.1, 0.3)
        time.sleep(sleep_time)
    LAST_REQUEST_TIME = time.time()

def weatherapi_to_accu_icon(code, is_day=1):
    day_map = {1000: 1, 1003: 3, 1006: 4, 1009: 4, 1030: 11, 1063: 12, 1066: 19, 1069: 19, 1072: 12, 1087: 15, 1114: 19, 1117: 21, 1135: 11, 1147: 11, 1150: 12, 1153: 12, 1168: 12, 1171: 14, 1180: 12, 1183: 13, 1186: 13, 1189: 14, 1192: 15, 1195: 15, 1198: 13, 1201: 15, 1204: 19, 1207: 20, 1210: 19, 1213: 20, 1216: 20, 1219: 21, 1222: 21, 1225: 21, 1237: 21, 1240: 12, 1243: 13, 1246: 15, 1249: 19, 1252: 20, 1255: 19, 1258: 20, 1261: 19, 1264: 21, 1273: 15, 1276: 16, 1279: 19, 1282: 21}
    night_map = {1000: 33, 1003: 35, 1006: 36, 1009: 36}
    if is_day:
        return day_map.get(code, 1)
    else:
        return night_map.get(code, day_map.get(code, 33))

def weatherapi_to_text(code):
    texts = {1000: "Despejado", 1003: "Parcialmente Nublado", 1006: "Nublado", 1009: "Cubierto", 1030: "Neblina", 1063: "Posible Lluvia", 1066: "Posible Nieve", 1087: "Tormenta Eléctrica", 1114: "Nieve Ventosa", 1117: "Ventisca", 1135: "Niebla", 1150: "Llovizna", 1183: "Lluvia Ligera", 1186: "Lluvia Moderada", 1189: "Lluvia", 1192: "Lluvia Fuerte", 1195: "Lluvia Intensa", 1210: "Nieve Ligera", 1213: "Nieve", 1219: "Nieve Moderada", 1225: "Nieve Fuerte", 1273: "Tormenta", 1276: "Tormenta Fuerte"}
    return texts.get(code, "Despejado")

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    query = query.replace('+', ' ').replace(',', ' ').strip()

    if not query or len(query) < 2:
        return Response('<?xml version="1.0" encoding="UTF-8"?><adc_database></adc_database>', mimetype='application/xml')

    try:
        params = {"name": query, "count": 10, "language": "es", "format": "json"}
        resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])

        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<adc_database>']

        for city in results:
            lat = city.get('latitude', 0)
            lon = city.get('longitude', 0)

            # EXACT 6 decimal places
            lat_formatted = f"{lat:.6f}"
            lon_formatted = f"{lon:.6f}"

            lat_key = lat_formatted.replace('.', '_')
            lon_key = lon_formatted.replace('.', '_')
            safe_key = f"{lat_key}__{lon_key}"

            xml_parts.append('  <location>')
            xml_parts.append(f'    <City>{city.get("name", "Unknown")}</City>')
            xml_parts.append(f'    <State>{city.get("admin1", city.get("country", ""))}</State>')
            xml_parts.append(f'    <Country>{city.get("country", "XX")}</Country>')
            xml_parts.append(f'    <locationKey>{safe_key}</locationKey>')
            xml_parts.append('  </location>')

        xml_parts.append('</adc_database>')
        xml_str = '\n'.join(xml_parts)

        print(f"XML: {len(xml_str)} bytes for '{query}'")
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return Response('<?xml version="1.0" encoding="UTF-8"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location') or request.args.get('locationKey')

    try:
        lat, lon = None, None

        if location_key and location_key not in ['null', '', 'None']:
            key_clean = location_key.strip()
            if '__' in key_clean:
                try:
                    parts = key_clean.split('__')
                    if len(parts) == 2:
                        lat = float(parts[0].replace('_', '.'))
                        lon = float(parts[1].replace('_', '.'))
                except:
                    pass
            elif '_' in key_clean:
                try:
                    match = re.match(r'(-?\d+_\d+)__?(-?\d+_\d+)', key_clean)
                    if match:
                        lat = float(match.group(1).replace('_', '.'))
                        lon = float(match.group(2).replace('_', '.'))
                except:
                    pass

        if lat is None and lat_raw and lon_raw:
            if lat_raw not in ['null', '0.0', '0', ''] and lon_raw not in ['null', '0.0', '0', '']:
                try:
                    lat = float(lat_raw)
                    lon = float(lon_raw)
                except:
                    pass

        if lat is None or lon is None:
            lat, lon = -33.4489, -70.6693

        cached_data = get_cached_weather(lat, lon)
        if cached_data:
            return generate_weather_xml_weatherapi(cached_data)

        return fetch_weatherapi(lat, lon)

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return generate_fallback_xml()

def fetch_weatherapi(lat, lon):
    params = {"key": WEATHERAPI_KEY, "q": f"{lat},{lon}", "days": 5, "aqi": "no", "alerts": "no"}

    for attempt in range(3):
        try:
            rate_limit()
            resp = requests.get(WEATHERAPI_URL, params=params, timeout=10)
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            set_cached_weather(lat, lon, data)
            return generate_weather_xml_weatherapi(data)
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
                continue
            raise

def generate_weather_xml_weatherapi(data):
    try:
        current = data.get('current', {})
        forecast = data.get('forecast', {}).get('forecastday', [])

        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<adc_database>', '  <currentconditions>']

        temp_c = current.get('temp_c', 15)
        temp_f = int(c_to_f(temp_c))
        is_day = current.get('is_day', 1)
        condition = current.get('condition', {})
        code = condition.get('code', 1000)

        xml_parts.append(f'    <temperature>{temp_f}</temperature>')
        xml_parts.append(f'    <weathericon>{weatherapi_to_accu_icon(code, is_day)}</weathericon>')
        xml_parts.append(f'    <weathertext>{weatherapi_to_text(code)}</weathertext>')
        xml_parts.append(f'    <humidity>{current.get("humidity", 50)}</humidity>')
        xml_parts.append(f'    <isdaytime>{"true" if is_day else "false"}</isdaytime>')
        xml_parts.append('  </currentconditions>')
        xml_parts.append('  <forecast>')

        for day_data in forecast[:5]:
            day_info = day_data.get('day', {})
            max_c = day_info.get('maxtemp_c', 20)
            min_c = day_info.get('mintemp_c', 10)
            max_f = int(c_to_f(max_c))
            min_f = int(c_to_f(min_c))
            day_condition = day_info.get('condition', {})
            day_code = day_condition.get('code', 1000)

            xml_parts.append('    <day>')
            xml_parts.append(f'      <obsdate>{day_data.get("date", "")}</obsdate>')
            xml_parts.append(f'      <hightemperature>{max_f}</hightemperature>')
            xml_parts.append(f'      <lowtemperature>{min_f}</lowtemperature>')
            xml_parts.append(f'      <weathericon>{weatherapi_to_accu_icon(day_code, 1)}</weathericon>')
            xml_parts.append(f'      <weathertext>{weatherapi_to_text(day_code)}</weathertext>')
            xml_parts.append('    </day>')

        xml_parts.append('  </forecast>')
        xml_parts.append('</adc_database>')

        xml_str = '\n'.join(xml_parts)
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        print(f"ERROR: {e}")
        raise

def generate_fallback_xml():
    fallback = """<?xml version="1.0" encoding="UTF-8"?>
<adc_database>
  <currentconditions>
    <temperature>65</temperature>
    <weathericon>3</weathericon>
    <weathertext>Service Temporarily Unavailable</weathertext>
    <humidity>50</humidity>
    <isdaytime>true</isdaytime>
  </currentconditions>
</adc_database>"""
    return Response(fallback, mimetype='application/xml')

@app.route('/')
def index():
    return "<h1>TSF Weather Server</h1>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

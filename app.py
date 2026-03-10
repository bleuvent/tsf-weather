from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import traceback
import time
import random
import re

app = Flask(__name__)

# ============================================================
# CONFIGURACIÓN DE APIs
# ============================================================
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

WEATHERAPI_KEY = os.environ.get("WEATHERAPI_KEY", "")
WEATHERAPI_URL = "http://api.weatherapi.com/v1/forecast.json"

USE_WEATHERAPI = bool(WEATHERAPI_KEY)

# ============================================================
# CACHE SIMPLE EN MEMORIA
# ============================================================
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
            print(f"CACHE HIT: {key} (age: {age.seconds}s)")
            return data
    return None

def set_cached_weather(lat, lon, data):
    key = get_cache_key(lat, lon)
    weather_cache[key] = (data, datetime.now())
    print(f"CACHE SET: {key}")

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
    day_map = {
        1000: 1, 1003: 3, 1006: 4, 1009: 4, 1030: 11, 1063: 12, 1066: 19,
        1069: 19, 1072: 12, 1087: 15, 1114: 19, 1117: 21, 1135: 11, 1147: 11,
        1150: 12, 1153: 12, 1168: 12, 1171: 14, 1180: 12, 1183: 13, 1186: 13,
        1189: 14, 1192: 15, 1195: 15, 1198: 13, 1201: 15, 1204: 19, 1207: 20,
        1210: 19, 1213: 20, 1216: 20, 1219: 21, 1222: 21, 1225: 21, 1237: 21,
        1240: 12, 1243: 13, 1246: 15, 1249: 19, 1252: 20, 1255: 19, 1258: 20,
        1261: 19, 1264: 21, 1273: 15, 1276: 16, 1279: 19, 1282: 21,
    }
    night_map = {1000: 33, 1003: 35, 1006: 36, 1009: 36}
    if is_day:
        return day_map.get(code, 1)
    else:
        return night_map.get(code, day_map.get(code, 33))

def weatherapi_to_text(code):
    texts = {
        1000: "Despejado", 1003: "Parcialmente Nublado", 1006: "Nublado",
        1009: "Cubierto", 1030: "Neblina", 1063: "Posible Lluvia",
        1066: "Posible Nieve", 1087: "Tormenta Eléctrica", 1114: "Nieve Ventosa",
        1117: "Ventisca", 1135: "Niebla", 1150: "Llovizna", 1183: "Lluvia Ligera",
        1186: "Lluvia Moderada", 1189: "Lluvia", 1192: "Lluvia Fuerte",
        1195: "Lluvia Intensa", 1210: "Nieve Ligera", 1213: "Nieve",
        1219: "Nieve Moderada", 1225: "Nieve Fuerte", 1273: "Tormenta",
        1276: "Tormenta Fuerte",
    }
    return texts.get(code, "Despejado")

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    query = query.replace('+', ' ').replace(',', ' ').strip()

    if not query or len(query) < 2:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', 
                       mimetype='application/xml')

    try:
        params = {
            "name": query,
            "count": 10,
            "language": "es",
            "format": "json"
        }

        resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])

        root = ET.Element("adc_database")

        for city in results:
            loc = ET.SubElement(root, "location")

            lat = city.get('latitude', 0)
            lon = city.get('longitude', 0)
            
            # ============================================================
            # FORMATO CORREGIDO: Doble guion bajo para separar lat/lon
            # ============================================================
            lat_str = f"{lat:+.6f}"
            lon_str = f"{lon:+.6f}"
            
            # Formato: 19_450830__-70_694720 (doble guion bajo entre lat y lon)
            safe_key = f"{lat_str.replace('.', '_').replace('+', '')}__{lon_str.replace('.', '_').replace('+', '')}"

            print(f"Generando key: {safe_key} para {city.get('name')}")

            # ETIQUETAS AccuWeather v1 (2014)
            ET.SubElement(loc, "City").text = city.get('name', 'Unknown')
            ET.SubElement(loc, "State").text = city.get('admin1', city.get('country', ''))
            ET.SubElement(loc, "Country").text = city.get('country', 'XX')
            ET.SubElement(loc, "locationKey").text = safe_key
            ET.SubElement(loc, "key").text = safe_key
            ET.SubElement(loc, "city").text = city.get('name', 'Unknown')
            ET.SubElement(loc, "state").text = city.get('admin1', city.get('country', ''))
            ET.SubElement(loc, "country").text = city.get('country', 'XX')
            ET.SubElement(loc, "cityname").text = city.get('name', 'Unknown')
            ET.SubElement(loc, "statename").text = city.get('admin1', city.get('country', ''))
            ET.SubElement(loc, "countryname").text = city.get('country', 'XX')
            ET.SubElement(loc, "latitude").text = str(lat)
            ET.SubElement(loc, "longitude").text = str(lon)

        xml_str = ET.tostring(root, encoding='unicode')
        print(f"XML generado para '{query}': {len(xml_str)} bytes")
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        print(f"ERROR en city-find: {str(e)}")
        traceback.print_exc()
        return Response('<?xml version="1.0"?><adc_database></adc_database>', 
                       mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location')
    
    print(f"=== NUEVA PETICIÓN ===")
    print(f"slat={lat_raw}, slon={lon_raw}, location={location_key}")

    try:
        lat, lon = None, None

        # ============================================================
        # PRIORIDAD 1: locationKey desde búsqueda manual
        # ============================================================
        if location_key and location_key not in ['null', '', 'None']:
            print(f"Procesando location_key: '{location_key}'")
            key_clean = location_key.strip()
            
            # Formato con doble guion bajo (nuevo formato)
            if '__' in key_clean:
                try:
                    parts = key_clean.split('__')
                    if len(parts) == 2:
                        lat_part = parts[0].replace('_', '.')
                        lon_part = parts[1].replace('_', '.')
                        lat = float(lat_part)
                        lon = float(lon_part)
                        print(f"Parseado con __: lat={lat}, lon={lon}")
                except Exception as e:
                    print(f"Error parseando formato __: {e}")
            
            # Formato con guion bajo simple (fallback)
            elif '_' in key_clean:
                try:
                    # Regex para formato: 19_45083_-70_69472
                    match = re.match(r'(-?\d+_\d+)__?(-?\d+_\d+)', key_clean)
                    if match:
                        lat_str = match.group(1).replace('_', '.')
                        lon_str = match.group(2).replace('_', '.')
                        lat = float(lat_str)
                        lon = float(lon_str)
                    else:
                        # Dividir por el guion bajo del medio (aproximado)
                        parts = key_clean.split('_')
                        if len(parts) >= 2:
                            mid = len(parts) // 2
                            lat_str = '.'.join(['_'.join(parts[:mid])])
                            lon_str = '.'.join(['_'.join(parts[mid:])])
                            lat = float(lat_str)
                            lon = float(lon_str)
                    
                    print(f"Parseado con _: lat={lat}, lon={lon}")
                except Exception as e:
                    print(f"Error parseando formato _: {e}")

        # ============================================================
        # PRIORIDAD 2: slat/slon (auto-localización)
        # ============================================================
        if lat is None and lat_raw and lon_raw:
            if lat_raw not in ['null', '0.0', '0', ''] and lon_raw not in ['null', '0.0', '0', '']:
                try:
                    lat = float(lat_raw)
                    lon = float(lon_raw)
                    print(f"Usando slat/slon: {lat}, {lon}")
                except ValueError:
                    print(f"Error parseando slat/slon: {lat_raw}, {lon_raw}")

        # ============================================================
        # DEFAULT: Santiago
        # ============================================================
        if lat is None or lon is None:
            print(f"USANDO DEFAULT. lat era: {lat}, lon era: {lon}")
            lat, lon = -33.4489, -70.6693
        elif lat == 0.0 and lon == 0.0:
            print("ADVERTENCIA: Coordenadas 0,0 detectadas, usando default")
            lat, lon = -33.4489, -70.6693

        print(f"FINAL: lat={lat}, lon={lon}")

        # Verificar cache
        cached_data = get_cached_weather(lat, lon)
        if cached_data:
            print("Usando datos cacheados")
            return generate_weather_xml_weatherapi(cached_data)

        # Llamar a WeatherAPI
        return fetch_weatherapi(lat, lon)

    except Exception as e:
        print(f"ERROR en weather-data: {str(e)}")
        traceback.print_exc()
        
        if lat and lon:
            stale_data = get_cached_weather(lat, lon)
            if stale_data:
                return generate_weather_xml_weatherapi(stale_data)
        
        return generate_fallback_xml()

def fetch_weatherapi(lat, lon):
    params = {
        "key": WEATHERAPI_KEY,
        "q": f"{lat},{lon}",
        "days": 5,
        "aqi": "no",
        "alerts": "no"
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            rate_limit()
            print(f"WeatherAPI intento {attempt + 1}/{max_retries}...")
            
            resp = requests.get(WEATHERAPI_URL, params=params, timeout=10)
            
            if resp.status_code == 429:
                wait_time = 2 * (attempt + 1)
                time.sleep(wait_time)
                continue
            
            resp.raise_for_status()
            data = resp.json()
            
            print("WeatherAPI: ÉXITO")
            set_cached_weather(lat, lon, data)
            return generate_weather_xml_weatherapi(data)
            
        except Exception as e:
            print(f"WeatherAPI error intento {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise

def generate_weather_xml_weatherapi(data):
    try:
        current = data.get('current', {})
        forecast = data.get('forecast', {}).get('forecastday', [])

        root = ET.Element("adc_database")

        curr_node = ET.SubElement(root, "currentconditions")
        
        temp_c = current.get('temp_c', 15)
        temp_f = int(c_to_f(temp_c))
        is_day = current.get('is_day', 1)
        condition = current.get('condition', {})
        code = condition.get('code', 1000)
        
        ET.SubElement(curr_node, "temperature").text = str(temp_f)
        ET.SubElement(curr_node, "weathericon").text = str(weatherapi_to_accu_icon(code, is_day))
        ET.SubElement(curr_node, "weathertext").text = weatherapi_to_text(code)
        ET.SubElement(curr_node, "humidity").text = str(current.get('humidity', 50))
        ET.SubElement(curr_node, "isdaytime").text = "true" if is_day else "false")

        forecast_node = ET.SubElement(root, "forecast")
        
        for day_data in forecast[:5]:
            day_node = ET.SubElement(forecast_node, "day")
            date = day_data.get('date', '')
            day_info = day_data.get('day', {})
            
            ET.SubElement(day_node, "obsdate").text = date
            
            max_c = day_info.get('maxtemp_c', 20)
            min_c = day_info.get('mintemp_c', 10)
            max_f = int(c_to_f(max_c))
            min_f = int(c_to_f(min_c))
            
            ET.SubElement(day_node, "hightemperature").text = str(max_f)
            ET.SubElement(day_node, "lowtemperature").text = str(min_f)
            
            day_condition = day_info.get('condition', {})
            day_code = day_condition.get('code', 1000)
            
            ET.SubElement(day_node, "weathericon").text = str(weatherapi_to_accu_icon(day_code, 1))
            ET.SubElement(day_node, "weathertext").text = weatherapi_to_text(day_code)

        xml_str = ET.tostring(root, encoding='unicode')
        print(f"WeatherAPI XML: {len(xml_str)} bytes")
        return Response(xml_str, mimetype='application/xml')
        
    except Exception as e:
        print(f"ERROR generando XML: {e}")
        raise

def generate_fallback_xml():
    fallback = f'''<?xml version="1.0"?>
<adc_database>
    <currentconditions>
        <temperature>65</temperature>
        <weathericon>3</weathericon>
        <weathertext>Service Temporarily Unavailable</weathertext>
        <humidity>50</humidity>
        <isdaytime>true</isdaytime>
    </currentconditions>
</adc_database>'''
    return Response(fallback, mimetype='application/xml')

@app.route('/')
def index():
    api_status = "WeatherAPI" if USE_WEATHERAPI else "Open-Meteo"
    return f"<h1>TSF Weather Server</h1><p>API: {api_status}</p><p>Cache: {len(weather_cache)}</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

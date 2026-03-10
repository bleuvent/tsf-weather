from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import traceback
import time
import random

app = Flask(__name__)

# ============================================================
# CONFIGURACIÓN DE APIs
# ============================================================
# Opción A: Open-Meteo (gratis, sin key, pero rate limitado)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Opción B: WeatherAPI (gratis 1M/mes, requiere key, más estable)
# Regístrate gratis en https://www.weatherapi.com/ y pon tu key aquí:
WEATHERAPI_KEY = os.environ.get("WEATHERAPI_KEY", "")  # O ponla directamente: "tu-key-aqui"
WEATHERAPI_URL = "http://api.weatherapi.com/v1/forecast.json"

# Forzar uso de WeatherAPI si tenemos key, sino Open-Meteo
USE_WEATHERAPI = bool(WEATHERAPI_KEY)

# ============================================================
# CACHE SIMPLE EN MEMORIA
# ============================================================
weather_cache = {}
CACHE_DURATION = timedelta(minutes=30)
LAST_REQUEST_TIME = 0
MIN_REQUEST_INTERVAL = 0.5 if USE_WEATHERAPI else 2.0  # WeatherAPI permite más rápido

def get_cache_key(lat, lon):
    """Redondear coordenadas a 1 decimal"""
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

# ============================================================
# MAPEO DE CÓDIGOS WeatherAPI -> AccuWeather
# ============================================================
def weatherapi_to_accu_icon(code, is_day=1):
    """
    Mapea códigos de WeatherAPI a iconos de AccuWeather
    WeatherAPI codes: https://www.weatherapi.com/docs/weather_conditions.json
    """
    day_map = {
        1000: 1,   # Sunny
        1003: 3,   # Partly cloudy
        1006: 4,   # Cloudy
        1009: 4,   # Overcast
        1030: 11,  # Mist
        1063: 12,  # Patchy rain possible
        1066: 19,  # Patchy snow possible
        1069: 19,  # Patchy sleet possible
        1072: 12,  # Patchy freezing drizzle possible
        1087: 15,  # Thundery outbreaks possible
        1114: 19,  # Blowing snow
        1117: 21,  # Blizzard
        1135: 11,  # Fog
        1147: 11,  # Freezing fog
        1150: 12,  # Patchy light drizzle
        1153: 12,  # Light drizzle
        1168: 12,  # Freezing drizzle
        1171: 14,  # Heavy freezing drizzle
        1180: 12,  # Patchy light rain
        1183: 13,  # Light rain
        1186: 13,  # Moderate rain at times
        1189: 14,  # Moderate rain
        1192: 15,  # Heavy rain at times
        1195: 15,  # Heavy rain
        1198: 13,  # Light freezing rain
        1201: 15,  # Moderate or heavy freezing rain
        1204: 19,  # Light sleet
        1207: 20,  # Moderate or heavy sleet
        1210: 19,  # Patchy light snow
        1213: 20,  # Light snow
        1216: 20,  # Patchy moderate snow
        1219: 21,  # Moderate snow
        1222: 21,  # Patchy heavy snow
        1225: 21,  # Heavy snow
        1237: 21,  # Ice pellets
        1240: 12,  # Light rain shower
        1243: 13,  # Moderate or heavy rain shower
        1246: 15,  # Torrential rain shower
        1249: 19,  # Light sleet showers
        1252: 20,  # Moderate or heavy sleet showers
        1255: 19,  # Light snow showers
        1258: 20,  # Moderate or heavy snow showers
        1261: 19,  # Light showers of ice pellets
        1264: 21,  # Moderate or heavy showers of ice pellets
        1273: 15,  # Patchy light rain with thunder
        1276: 16,  # Moderate or heavy rain with thunder
        1279: 19,  # Patchy light snow with thunder
        1282: 21,  # Moderate or heavy snow with thunder
    }
    
    night_map = {
        1000: 33,  # Clear
        1003: 35,  # Partly cloudy
        1006: 36,  # Cloudy
        1009: 36,  # Overcast
    }
    
    if is_day:
        return day_map.get(code, 1)
    else:
        return night_map.get(code, day_map.get(code, 33))

def weatherapi_to_text(code):
    """Textos en español para códigos WeatherAPI"""
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
        # Usar Open-Meteo para geocoding (suele ser más permisivo para esto)
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
            safe_key = f"{str(lat).replace('.', '_')}_{str(lon).replace('.', '_')}"

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

        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        print(f"ERROR en city-find: {str(e)}")
        return Response('<?xml version="1.0"?><adc_database></adc_database>', 
                       mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location')

    try:
        lat, lon = None, None

        if location_key and '_' in location_key:
            parts = location_key.split('_')
            lat = float(parts[0].replace('_', '.'))
            lon = float(parts[1].replace('_', '.'))
        elif lat_raw and lon_raw:
            lat = float(lat_raw)
            lon = float(lon_raw)

        if lat is None or lon is None:
            lat, lon = -33.4489, -70.6693

        print(f"Consultando clima para: lat={lat}, lon={lon}")
        print(f"Cache key: {get_cache_key(lat, lon)}")
        print(f"Usando: {'WeatherAPI' if USE_WEATHERAPI else 'Open-Meteo'}")

        # Verificar cache
        cached_data = get_cached_weather(lat, lon)
        if cached_data:
            print("Usando datos cacheados")
            if USE_WEATHERAPI:
                return generate_weather_xml_weatherapi(cached_data)
            else:
                return generate_weather_xml_openmeteo(cached_data)

        # ============================================================
        # LLAMADA A WeatherAPI (más estable)
        # ============================================================
        if USE_WEATHERAPI:
            return fetch_weatherapi(lat, lon)
        else:
            return fetch_openmeteo(lat, lon)

    except Exception as e:
        print(f"ERROR en weather-data: {str(e)}")
        print(traceback.format_exc())
        
        # Intentar cache viejo
        if lat and lon:
            stale_data = get_cached_weather(lat, lon)
            if stale_data:
                print("Usando cache viejo por error")
                if USE_WEATHERAPI:
                    return generate_weather_xml_weatherapi(stale_data)
                else:
                    return generate_weather_xml_openmeteo(stale_data)
        
        # Fallback
        return generate_fallback_xml()

def fetch_weatherapi(lat, lon):
    """Obtiene datos de WeatherAPI"""
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
                print(f"WeatherAPI rate limit, esperando {wait_time}s...")
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

def fetch_openmeteo(lat, lon):
    """Obtiene datos de Open-Meteo (backup)"""
    params = {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "current": "temperature_2m,relative_humidity_2m,weather_code,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": 5
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            rate_limit()
            print(f"Open-Meteo intento {attempt + 1}/{max_retries}...")
            
            resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
            
            if resp.status_code == 429:
                wait_time = 3 * (attempt + 1)
                print(f"Open-Meteo 429, esperando {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            resp.raise_for_status()
            data = resp.json()
            
            print("Open-Meteo: ÉXITO")
            set_cached_weather(lat, lon, data)
            return generate_weather_xml_openmeteo(data)
            
        except Exception as e:
            print(f"Open-Meteo error intento {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise

def generate_weather_xml_weatherapi(data):
    """Genera XML desde datos de WeatherAPI"""
    try:
        current = data.get('current', {})
        forecast = data.get('forecast', {}).get('forecastday', [])
        location = data.get('location', {})

        root = ET.Element("adc_database")

        # Condiciones actuales
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
        ET.SubElement(curr_node, "isdaytime").text = "true" if is_day else "false"

        # Pronóstico
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
        print(f"ERROR generando XML WeatherAPI: {e}")
        raise

def generate_weather_xml_openmeteo(data):
    """Genera XML desde datos de Open-Meteo (código anterior)"""
    try:
        current = data.get('current', {})
        daily = data.get('daily', {})

        is_day = current.get('is_day', 1) == 1

        root = ET.Element("adc_database")

        curr_node = ET.SubElement(root, "currentconditions")
        ET.SubElement(curr_node, "weathertext").text = get_weather_text_openmeteo(current.get('weather_code', 0))
        icon_code = get_accu_icon_openmeteo(current.get('weather_code', 0), is_day)
        ET.SubElement(curr_node, "weathericon").text = str(icon_code)

        temp_c = current.get('temperature_2m', 15)
        temp_f = int(c_to_f(temp_c))
        ET.SubElement(curr_node, "temperature").text = str(temp_f)

        ET.SubElement(curr_node, "humidity").text = str(current.get('relative_humidity_2m', 50))
        ET.SubElement(curr_node, "isdaytime").text = "true" if is_day else "false"

        forecast_node = ET.SubElement(root, "forecast")
        
        daily_times = daily.get('time', [])
        daily_codes = daily.get('weather_code', [])
        daily_max = daily.get('temperature_2m_max', [])
        daily_min = daily.get('temperature_2m_min', [])

        for i in range(min(5, len(daily_times))):
            day_node = ET.SubElement(forecast_node, "day")
            ET.SubElement(day_node, "obsdate").text = daily_times[i]

            max_c = daily_max[i] if i < len(daily_max) else 15
            min_c = daily_min[i] if i < len(daily_min) else 10
            
            max_f = int(c_to_f(max_c))
            min_f = int(c_to_f(min_c))

            ET.SubElement(day_node, "hightemperature").text = str(max_f)
            ET.SubElement(day_node, "lowtemperature").text = str(min_f)
            
            code = daily_codes[i] if i < len(daily_codes) else 0
            ET.SubElement(day_node, "weathericon").text = str(get_accu_icon_openmeteo(code, True))
            ET.SubElement(day_node, "weathertext").text = get_weather_text_openmeteo(code)

        xml_str = ET.tostring(root, encoding='unicode')
        print(f"Open-Meteo XML: {len(xml_str)} bytes")
        return Response(xml_str, mimetype='application/xml')
        
    except Exception as e:
        print(f"ERROR generando XML Open-Meteo: {e}")
        raise

def get_weather_text_openmeteo(code):
    texts = {
        0: "Despejado", 1: "Mayormente Despejado", 2: "Parcialmente Nublado", 3: "Nublado",
        45: "Niebla", 48: "Niebla con Escarcha", 51: "Llovizna Ligera", 53: "Llovizna",
        55: "Llovizna Intensa", 61: "Lluvia Ligera", 63: "Lluvia", 65: "Lluvia Fuerte",
        71: "Nieve Ligera", 73: "Nieve", 75: "Nieve Fuerte", 77: "Granizo",
        80: "Chubascos Ligeros", 81: "Chubascos", 82: "Chubascos Fuertes",
        95: "Tormenta", 96: "Tormenta con Granizo", 99: "Tormenta Fuerte"
    }
    return texts.get(code, "Despejado")

def get_accu_icon_openmeteo(code, is_day=True):
    icons_day = {
        0: 1, 1: 2, 2: 3, 3: 4, 45: 11, 48: 11, 51: 12, 53: 12, 55: 12,
        61: 13, 63: 14, 65: 15, 71: 19, 73: 20, 75: 21, 77: 19,
        80: 12, 81: 13, 82: 14, 85: 19, 86: 20, 95: 15, 96: 16, 99: 17
    }
    icons_night = {
        0: 33, 1: 34, 2: 35, 3: 36, 45: 37, 48: 37, 51: 39, 53: 39, 55: 39,
        61: 40, 63: 41, 65: 42, 71: 44, 73: 44, 75: 44, 77: 44,
        80: 39, 81: 40, 82: 41, 85: 44, 86: 44, 95: 42, 96: 42, 99: 42
    }
    return icons_day.get(code, 1) if is_day else icons_night.get(code, 33)

def generate_fallback_xml():
    """XML de fallback cuando todo falla"""
    fallback = f'''<?xml version="1.0"?>
<adc_database>
    <currentconditions>
        <temperature>65</temperature>
        <weathericon>3</weathericon>
        <weathertext>Service Temporarily Unavailable</weathertext>
        <humidity>50</humidity>
        <isdaytime>true</isdaytime>
    </currentconditions>
    <forecast>
        <day>
            <obsdate>{datetime.now().strftime('%Y-%m-%d')}</obsdate>
            <hightemperature>70</hightemperature>
            <lowtemperature>60</lowtemperature>
            <weathericon>3</weathericon>
            <weathertext>Unavailable</weathertext>
        </day>
    </forecast>
</adc_database>'''
    return Response(fallback, mimetype='application/xml')

@app.route('/')
def index():
    api_status = "WeatherAPI (con key)" if USE_WEATHERAPI else "Open-Meteo (sin key - puede fallar)"
    return f"<h1>TSF Weather Server</h1><p>API activa: {api_status}</p><p>Cache: {len(weather_cache)} ubicaciones</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
        

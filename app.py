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
    """
    Mapeo de códigos WeatherAPI a íconos AccuWeather (1-44)
    Códigos AccuWeather: 1-4 (soleado a nublado), 5-8 (lluvia), etc.
    """
    # Día
    day_map = {
        1000: 1,   # Soleado / Despejado
        1003: 3,   # Parcialmente nublado
        1006: 6,   # Nublado (CORREGIDO - antes era 4, ahora 6 para mostrar nublado real)
        1009: 7,   # Cubierto (CORREGIDO - antes era 4, ahora 7)
        1030: 11,  # Neblina
        1063: 12,  # Posible lluvia
        1066: 19,  # Posible nieve
        1069: 19,  # Posible aguanieve
        1072: 12,  # Llovizna helada
        1087: 15,  # Tormenta eléctrica
        1114: 19,  # Nieve ventosa
        1117: 21,  # Ventisca
        1135: 11,  # Niebla
        1147: 11,  # Niebla helada
        1150: 12,  # Llovizna ligera
        1153: 12,  # Llovizna
        1168: 12,  # Llovizna helada
        1171: 14,  # Llovizna fuerte helada
        1180: 12,  # Lluvia ligera
        1183: 13,  # Lluvia moderada
        1186: 13,  # Lluvia moderada
        1189: 14,  # Lluvia fuerte
        1192: 15,  # Lluvia muy fuerte
        1195: 15,  # Lluvia intensa
        1198: 13,  # Lluvia helada ligera
        1201: 15,  # Lluvia helada fuerte
        1204: 19,  # Aguanieve ligera
        1207: 20,  # Aguanieve fuerte
        1210: 19,  # Nieve ligera
        1213: 20,  # Nieve
        1216: 20,  # Nieve moderada
        1219: 21,  # Nieve fuerte
        1222: 21,  # Nieve muy fuerte
        1225: 21,  # Nieve intensa
        1237: 21,  # Granizo
        1240: 12,  # Chubasco ligero
        1243: 13,  # Chubasco moderado
        1246: 15,  # Chubasco fuerte
        1249: 19,  # Chubasco de aguanieve ligero
        1252: 20,  # Chubasco de aguanieve fuerte
        1255: 19,  # Chubasco de nieve ligero
        1258: 20,  # Chubasco de nieve fuerte
        1261: 19,  # Chubasco de granizo ligero
        1264: 21,  # Chubasco de granizo fuerte
        1273: 15,  # Lluvia con tormenta ligera
        1276: 16,  # Lluvia con tormenta
        1279: 19,  # Nieve con tormenta ligera
        1282: 21,  # Nieve con tormenta
    }
    
    # Noche (33+ para íconos nocturnos)
    night_map = {
        1000: 33,  # Despejado noche
        1003: 35,  # Parcialmente nublado noche
        1006: 36,  # Nublado noche (CORREGIDO)
        1009: 36,  # Cubierto noche (CORREGIDO)
    }
    
    if is_day:
        return day_map.get(code, 1)
    else:
        return night_map.get(code, day_map.get(code, 33))

def weatherapi_to_text(code):
    texts = {
        1000: "Despejado",
        1003: "Parcialmente Nublado",
        1006: "Nublado",
        1009: "Cubierto",
        1030: "Neblina",
        1063: "Posible Lluvia",
        1066: "Posible Nieve",
        1087: "Tormenta Eléctrica",
        1114: "Nieve Ventosa",
        1117: "Ventisca",
        1135: "Niebla",
        1150: "Llovizna",
        1183: "Lluvia Ligera",
        1186: "Lluvia Moderada",
        1189: "Lluvia",
        1192: "Lluvia Fuerte",
        1195: "Lluvia Intensa",
        1210: "Nieve Ligera",
        1213: "Nieve",
        1219: "Nieve Moderada",
        1225: "Nieve Fuerte",
        1273: "Tormenta",
        1276: "Tormenta Fuerte"
    }
    return texts.get(code, "Despejado")

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    query = query.replace('+', ' ').replace(',', ' ').strip()

    if not query or len(query) < 2:
        xml = '<?xml version="1.0" encoding="UTF-8"?><adc_database></adc_database>'
        return Response(xml, mimetype='application/xml', content_type='application/xml; charset=UTF-8')

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

            lat_formatted = f"{lat:.6f}"
            lon_formatted = f"{lon:.6f}"
            lat_key = lat_formatted.replace('.', '_')
            lon_key = lon_formatted.replace('.', '_')
            safe_key = f"{lat_key}__{lon_key}"

            city_name = city.get("name", "Unknown")
            admin1 = city.get("admin1", "")
            country = city.get("country", "XX")
            state = admin1 if admin1 else country

            xml_parts.append('  <location>')
            xml_parts.append(f'    <City>{city_name}</City>')
            xml_parts.append(f'    <State>{state}</State>')
            xml_parts.append(f'    <Country>{country}</Country>')
            xml_parts.append(f'    <locationKey>{safe_key}</locationKey>')
            xml_parts.append('  </location>')

        xml_parts.append('</adc_database>')
        xml_str = '\n'.join(xml_parts)

        print(f"CITY-FIND: {len(xml_str)} bytes for '{query}'")
        return Response(xml_str, mimetype='application/xml', content_type='application/xml; charset=UTF-8')

    except Exception as e:
        print(f"CITY-FIND ERROR: {str(e)}")
        xml = '<?xml version="1.0" encoding="UTF-8"?><adc_database></adc_database>'
        return Response(xml, mimetype='application/xml', content_type='application/xml; charset=UTF-8')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location') or request.args.get('locationKey')

    print(f"WEATHER-REQ: slat={lat_raw}, slon={lon_raw}, key={location_key}")

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
            return generate_weather_xml(cached_data, lat, lon)

        return fetch_weatherapi(lat, lon)

    except Exception as e:
        print(f"WEATHER ERROR: {str(e)}")
        return generate_fallback_xml(lat, lon)

def fetch_weatherapi(lat, lon):
    if not WEATHERAPI_KEY:
        return generate_fallback_xml(lat, lon)
        
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
            return generate_weather_xml(data, lat, lon)
        except Exception as e:
            print(f"Fetch attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(1)
                continue
            return generate_fallback_xml(lat, lon)

def generate_weather_xml(data, lat, lon):
    try:
        current = data.get('current', {})
        forecast = data.get('forecast', {}).get('forecastday', [])
        location = data.get('location', {})

        lat_formatted = f"{lat:.6f}"
        lon_formatted = f"{lon:.6f}"
        lat_key = lat_formatted.replace('.', '_')
        lon_key = lon_formatted.replace('.', '_')
        safe_key = f"{lat_key}__{lon_key}"

        city = location.get("name", "Unknown")
        state = location.get("region", "")
        country = location.get("country", "XX")
        if not state:
            state = country

        temp_c = current.get('temp_c', 15)
        temp_f = int(c_to_f(temp_c))
        is_day = current.get('is_day', 1)
        condition = current.get('condition', {})
        code = condition.get('code', 1000)
        weather_text = weatherapi_to_text(code)
        weather_icon = weatherapi_to_accu_icon(code, is_day)
        humidity = current.get("humidity", 50)
        obs_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # DEBUG: Imprimir en logs qué está recibiendo y enviando
        print(f"DEBUG: code={code}, is_day={is_day}, icon={weather_icon}, text={weather_text}")

        # LEGACY ACCUWEATHER XML FORMAT
        xml_parts = []
        xml_parts.append('<?xml version="1.0" encoding="UTF-8"?>')
        xml_parts.append('<adc_database>')
        xml_parts.append('  <CurrentConditions>')
        xml_parts.append(f'    <City>{city}</City>')
        xml_parts.append(f'    <State>{state}</State>')
        xml_parts.append(f'    <Country>{country}</Country>')
        xml_parts.append(f'    <locationKey>{safe_key}</locationKey>')
        xml_parts.append(f'    <Temperature>{temp_f}</Temperature>')
        xml_parts.append(f'    <RealFeelTemperature>{temp_f}</RealFeelTemperature>')
        xml_parts.append(f'    <WeatherIcon>{weather_icon}</WeatherIcon>')
        xml_parts.append(f'    <WeatherText>{weather_text}</WeatherText>')
        xml_parts.append(f'    <RelativeHumidity>{humidity}</RelativeHumidity>')
        xml_parts.append(f'    <IsDayTime>{"true" if is_day else "false"}</IsDayTime>')
        xml_parts.append(f'    <LocalObservationDateTime>{obs_time}</LocalObservationDateTime>')
        xml_parts.append(f'    <Latitude>{lat}</Latitude>')
        xml_parts.append(f'    <Longitude>{lon}</Longitude>')
        xml_parts.append('  </CurrentConditions>')
        xml_parts.append('  <forecast>')
        
        for day_data in forecast[:5]:
            day_info = day_data.get('day', {})
            max_c = day_info.get('maxtemp_c', 20)
            min_c = day_info.get('mintemp_c', 10)
            max_f = int(c_to_f(max_c))
            min_f = int(c_to_f(min_c))
            day_condition = day_info.get('condition', {})
            day_code = day_condition.get('code', 1000)
            day_text = weatherapi_to_text(day_code)
            day_icon = weatherapi_to_accu_icon(day_code, 1)
            date_str = day_data.get("date", "")

            xml_parts.append('    <day>')
            xml_parts.append(f'      <obsdate>{date_str}</obsdate>')
            xml_parts.append(f'      <hightemperature>{max_f}</hightemperature>')
            xml_parts.append(f'      <lowtemperature>{min_f}</lowtemperature>')
            xml_parts.append(f'      <weathericon>{day_icon}</weathericon>')
            xml_parts.append(f'      <weathertext>{day_text}</weathertext>')
            xml_parts.append('    </day>')

        xml_parts.append('  </forecast>')
        xml_parts.append('</adc_database>')

        xml_str = '\n'.join(xml_parts)
        print(f"WEATHER: {len(xml_str)} bytes for {city}, icon={weather_icon}")
        
        return Response(xml_str, mimetype='application/xml', content_type='application/xml; charset=UTF-8')

    except Exception as e:
        print(f"XML GEN ERROR: {e}")
        return generate_fallback_xml(lat, lon)

def generate_fallback_xml(lat=-33.4489, lon=-70.6693):
    lat_formatted = f"{lat:.6f}"
    lon_formatted = f"{lon:.6f}"
    lat_key = lat_formatted.replace('.', '_')
    lon_key = lon_formatted.replace('.', '_')
    safe_key = f"{lat_key}__{lon_key}"
    obs_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<adc_database>
  <CurrentConditions>
    <City>Santiago</City>
    <State>Region Metropolitana</State>
    <Country>Chile</Country>
    <locationKey>{safe_key}</locationKey>
    <Temperature>65</Temperature>
    <RealFeelTemperature>65</RealFeelTemperature>
    <WeatherIcon>3</WeatherIcon>
    <WeatherText>Service Temporarily Unavailable</WeatherText>
    <RelativeHumidity>50</RelativeHumidity>
    <IsDayTime>true</IsDayTime>
    <LocalObservationDateTime>{obs_time}</LocalObservationDateTime>
    <Latitude>{lat}</Latitude>
    <Longitude>{lon}</Longitude>
  </CurrentConditions>
</adc_database>"""
    
    return Response(xml, mimetype='application/xml', content_type='application/xml; charset=UTF-8')

@app.route('/')
def index():
    return "<h1>TSF Weather Server</h1><p>Legacy AccuWeather API Compatible</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    

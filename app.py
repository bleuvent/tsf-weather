from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
import os

app = Flask(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Base de datos en memoria para vincular IDs con coordenadas
location_db = {}

def c_to_f(c):
    return int((c * 9/5) + 32)

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    query = query.replace('+', ' ').strip()
    
    try:
        # TSF Shell prefiere pocos resultados pero con mucha info
        params = {"name": query, "count": 10, "language": "es", "format": "json"}
        resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        data = resp.json()
        results = data.get('results', [])
        
        # Estructura de respuesta idéntica al API original de 2014
        root = ET.Element("adc_database")
        for city in results:
            loc = ET.SubElement(root, "location")
            
            # Generamos un ID numérico corto (TSF a veces falla con IDs largos)
            city_id = str(abs(hash(f"{city.get('latitude')}{city.get('longitude')}")) % 100000)
            location_db[city_id] = {"lat": city.get('latitude'), "lon": city.get('longitude')}
            
            # Estas 3 etiquetas son el estándar "sagrado" de AccuWeather
            ET.SubElement(loc, "city").text = city.get('name', 'Ciudad')
            ET.SubElement(loc, "state").text = city.get('admin1', city.get('country', ''))
            ET.SubElement(loc, "locationKey").text = city_id
            
            # IMPORTANTE: TSF Shell busca esta etiqueta para llenar la lista visual
            ET.SubElement(loc, "cityname").text = f"{city.get('name')}, {city.get('country_code')}"

        xml_str = '<?xml version="1.0" encoding="utf-8" ?>' + ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location')
    
    lat, lon = None, None
    try:
        # Prioridad 1: Si viene por búsqueda manual (ID de nuestra memoria)
        if location_key and location_key in location_db:
            coords = location_db[location_key]
            lat, lon = coords['lat'], coords['lon']
        # Prioridad 2: Si viene por Fake GPS / Auto ubicación
        elif lat_raw and lon_raw:
            lat, lon = float(lat_raw), float(lon_raw)
        
        if lat is None: lat, lon = -33.44, -70.66

        params = {
            "latitude": lat, "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "is_day"],
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto", "forecast_days": 5
        }
        
        data = requests.get(OPEN_METEO_URL, params=params, timeout=10).json()
        current = data.get('current', {})
        daily = data.get('daily', {})
        is_day = current.get('is_day', 1) == 1
        
        root = ET.Element("adc_database")
        
        # Bloque de condiciones actuales
        curr = ET.SubElement(root, "currentconditions")
        # El widget necesita este texto para no quedar en blanco
        ET.SubElement(curr, "weathertext").text = "Sunny" if is_day else "Clear"
        icon_val = get_accu_icon(current.get('weather_code', 0), is_day)
        ET.SubElement(curr, "weathericon").text = str(icon_val).zfill(2)
        ET.SubElement(curr, "temperature").text = str(c_to_f(current.get('temperature_2m', 15)))
        ET.SubElement(curr, "humidity").text = str(int(current.get('relative_humidity_2m', 50)))
        ET.SubElement(curr, "isdaytime").text = "true" if is_day else "false"
        
        # Pronóstico
        forecast = ET.SubElement(root, "forecast")
        for i in range(min(5, len(daily.get('time', [])))):
            day = ET.SubElement(forecast, "day")
            ET.SubElement(day, "obsdate").text = daily.get('time', [])[i]
            ET.SubElement(day, "hightemperature").text = str(c_to_f(daily.get('temperature_2m_max', [])[i]))
            ET.SubElement(day, "lowtemperature").text = str(c_to_f(daily.get('temperature_2m_min', [])[i]))
            ET.SubElement(day, "weathericon").text = str(get_accu_icon(daily.get('weather_code', [])[i], True)).zfill(2)
        
        xml_output = '<?xml version="1.0" encoding="utf-8" ?>' + ET.tostring(root, encoding='unicode')
        return Response(xml_output, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

def get_accu_icon(code, is_day=True):
    icons = {0: 1, 1: 2, 2: 3, 3: 6, 45: 11, 51: 12, 61: 13, 63: 15, 80: 18, 95: 16}
    icon = icons.get(code, 1)
    if not is_day:
        night_icons = {1: 33, 2: 34, 3: 35, 6: 36}
        return night_icons.get(icon, icon + 32 if icon <= 8 else icon)
    return icon

@app.route('/')
def index(): return "TSF Active"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

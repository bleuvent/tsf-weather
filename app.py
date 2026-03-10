from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import os

app = Flask(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

def c_to_f(c):
    return int((c * 9/5) + 32)

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    query = query.replace('+', ' ').strip()
    
    try:
        params = {"name": query, "count": 5, "language": "es", "format": "json"}
        resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        data = resp.json()
        results = data.get('results', [])
        
        root = ET.Element("adc_database")
        for city in results:
            loc = ET.SubElement(root, "location")
            lat = "{:.2f}".format(city.get('latitude', 0))
            lon = "{:.2f}".format(city.get('longitude', 0))
            legacy_key = f"{lat},{lon}"
            
            # TSF Shell es muy sensible a estas etiquetas exactas
            ET.SubElement(loc, "city").text = city.get('name', 'City')[:15]
            ET.SubElement(loc, "state").text = city.get('admin1', city.get('country_code', ''))[:10]
            ET.SubElement(loc, "locationKey").text = legacy_key
            # Duplicamos para asegurar compatibilidad
            ET.SubElement(loc, "cityname").text = city.get('name', 'City')[:15]
            ET.SubElement(loc, "key").text = legacy_key

        xml_str = '<?xml version="1.0" encoding="utf-8" ?>' + ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat', '0')
    lon_raw = request.args.get('slon', '0')
    location_key = request.args.get('location')
    
    try:
        if location_key and ',' in location_key:
            parts = location_key.split(',')
            lat, lon = float(parts[0]), float(parts[1])
        else:
            lat, lon = float(lat_raw), float(lon_raw)

        params = {
            "latitude": lat, "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "is_day"],
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto", "forecast_days": 5
        }
        
        data = requests.get(OPEN_METEO_URL, params=params, timeout=10).json()
        current = data.get('current', {})
        daily = data.get('daily', {})
        
        root = ET.Element("adc_database")
        
        # Nodo de condiciones actuales (Simplificado al máximo)
        curr = ET.SubElement(root, "currentconditions")
        ET.SubElement(curr, "weathertext").text = "Clear"
        ET.SubElement(curr, "weathericon").text = str(get_accu_icon(current.get('weather_code', 0), current.get('is_day')))
        ET.SubElement(curr, "temperature").text = str(c_to_f(current.get('temperature_2m', 15)))
        ET.SubElement(curr, "humidity").text = str(int(current.get('relative_humidity_2m', 50)))
        
        # Nodo de pronóstico
        forecast = ET.SubElement(root, "forecast")
        for i in range(min(5, len(daily.get('time', [])))):
            day = ET.SubElement(forecast, "day")
            ET.SubElement(day, "obsdate").text = daily.get('time', [])[i]
            ET.SubElement(day, "hightemperature").text = str(c_to_f(daily.get('temperature_2m_max', [])[i]))
            ET.SubElement(day_node := day, "lowtemperature").text = str(c_to_f(daily.get('temperature_2m_min', [])[i]))
            ET.SubElement(day, "weathericon").text = str(get_accu_icon(daily.get('weather_code', [])[i], True))
        
        xml_output = '<?xml version="1.0" encoding="utf-8" ?>' + ET.tostring(root, encoding='unicode')
        return Response(xml_output, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

def get_weather_text(code):
    return "Sunny"

def get_accu_icon(code, is_day=True):
    icons = {0: 1, 1: 2, 2: 3, 3: 6, 45: 11, 51: 12, 61: 13, 63: 15, 80: 18, 95: 16}
    icon = icons.get(code, 1)
    if not is_day and icon <= 5: icon += 32 
    return icon

@app.route('/')
def index(): return "TSF Active"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

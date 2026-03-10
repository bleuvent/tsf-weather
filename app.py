from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import os

app = Flask(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

def c_to_f(c):
    return (c * 9/5) + 32

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    query = query.replace('+', ' ').replace(',', ' ').strip()
    
    if not query or len(query) < 2:
        return Response('<?xml version="1.0" encoding="utf-8" ?><adc_database></adc_database>', mimetype='application/xml')
    
    try:
        params = {"name": query, "count": 4, "language": "es", "format": "json"}
        resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        data = resp.json()
        results = data.get('results', [])
        
        root = ET.Element("adc_database")
        # TSF Shell suele buscar la lista dentro de 'citylist'
        citylist = ET.SubElement(root, "citylist")
        
        for city in results:
            loc = ET.SubElement(citylist, "location")
            
            lat = "{:.2f}".format(city.get('latitude', 0))
            lon = "{:.2f}".format(city.get('longitude', 0))
            legacy_key = f"{lat},{lon}"
            
            # Formato ultra-compatible AccuWeather v1
            ET.SubElement(loc, "city").text = city.get('name', 'City')[:15]
            ET.SubElement(loc, "state").text = city.get('admin1', city.get('country_code', ''))[:15]
            ET.SubElement(loc, "locationKey").text = legacy_key
            ET.SubElement(loc, "postalcode").text = "00000" # Relleno obligatorio

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
        lat, lon = None, None
        if location_key and ',' in location_key:
            parts = location_key.split(',')
            lat, lon = float(parts[0]), float(parts[1])
        else:
            lat, lon = round(float(lat_raw), 2), round(float(lon_raw), 2)
        
        if lat is None: lat, lon = -33.44, -70.66

        params = {
            "latitude": lat, "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "is_day"],
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto", "forecast_days": 5
        }
        
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        data = resp.json()
        current = data.get('current', {})
        daily = data.get('daily', {})
        is_day = (current.get('is_day', 1) == 1)
        
        root = ET.Element("adc_database")
        
        # Estructura de cabecera que TSF espera para validar
        units = ET.SubElement(root, "units")
        ET.SubElement(units, "temp").text = "f"
        ET.SubElement(units, "dist").text = "m"
        
        curr_node = ET.SubElement(root, "currentconditions")
        ET.SubElement(curr_node, "url").text = "http://www.accuweather.com"
        ET.SubElement(curr_node, "weathertext").text = get_weather_text(current.get('weather_code', 0))
        ET.SubElement(curr_node, "weathericon").text = str(get_accu_icon(current.get('weather_code', 0), is_day)).zfill(2)
        ET.SubElement(curr_node, "temperature").text = str(int(c_to_f(current.get('temperature_2m', 15))))
        ET.SubElement(curr_node, "humidity").text = str(current.get('relative_humidity_2m', 50)) + "%"
        ET.SubElement(curr_node, "observationtime").text = datetime.now().strftime("%I:%M %p")
        
        forecast_node = ET.SubElement(root, "forecast")
        for i in range(min(5, len(daily.get('time', [])))):
            day_node = ET.SubElement(forecast_node, "day")
            ET.SubElement(day_node, "obsdate").text = datetime.strptime(daily.get('time', [])[i], '%Y-%m-%d').strftime('%m/%d/%Y')
            ET.SubElement(day_node, "hightemperature").text = str(int(c_to_f(daily.get('temperature_2m_max', [])[i])))
            ET.SubElement(day_node, "lowtemperature").text = str(int(c_to_f(daily.get('temperature_2m_min', [])[i])))
            ET.SubElement(day_node, "weathericon").text = str(get_accu_icon(daily.get('weather_code', [])[i], True)).zfill(2)
        
        xml_output = '<?xml version="1.0" encoding="utf-8" ?>' + ET.tostring(root, encoding='unicode')
        return Response(xml_output, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

def get_weather_text(code):
    texts = {0: "Sunny", 1: "Clear", 2: "Partly Cloudy", 3: "Cloudy", 45: "Fog", 51: "Drizzle", 61: "Rain", 63: "Rain", 80: "Showers", 95: "Storm"}
    return texts.get(code, "Clear")

def get_accu_icon(code, is_day=True):
    icons = {0: 1, 1: 2, 2: 3, 3: 6, 45: 11, 51: 12, 61: 13, 63: 15, 80: 18, 95: 16}
    icon = icons.get(code, 1)
    if not is_day and icon <= 5: icon += 32 
    return icon

@app.route('/')
def index():
    return "TSF Weather Server Active"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

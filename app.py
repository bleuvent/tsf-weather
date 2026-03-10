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
        # Reducimos a 5 resultados para no saturar
        params = {"name": query, "count": 5, "language": "es", "format": "json"}
        resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        data = resp.json()
        results = data.get('results', [])
        
        root = ET.Element("adc_database")
        for city in results:
            loc = ET.SubElement(root, "location")
            lat = "{:.2f}".format(city.get('latitude', 0))
            lon = "{:.2f}".format(city.get('longitude', 0))
            # TSF Shell prefiere la coma sin espacios
            legacy_key = f"{lat},{lon}"
            
            # ORDEN CRITICO: El widget lee en orden secuencial
            ET.SubElement(loc, "city").text = city.get('name', 'City')[:15]
            ET.SubElement(loc, "state").text = city.get('admin1', 'ST')[:10]
            ET.SubElement(loc, "locationKey").text = legacy_key
            # Campos espejo para asegurar que no de Null
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
        
        # FIX NOCHE: Detectar correctamente si es de día
        is_day = current.get('is_day') == 1
        
        root = ET.Element("adc_database")
        
        # Nodo de condiciones actuales
        curr = ET.SubElement(root, "currentconditions")
        ET.SubElement(curr, "weathertext").text = "Clear"
        # FIX ICONO: zfill(2) asegura que sea "01" en vez de "1", vital para TSF
        icon_val = get_accu_icon(current.get('weather_code', 0), is_day)
        ET.SubElement(curr, "weathericon").text = str(icon_val).zfill(2)
        ET.SubElement(curr, "temperature").text = str(c_to_f(current.get('temperature_2m', 15)))
        ET.SubElement(curr, "humidity").text = str(int(current.get('relative_humidity_2m', 50)))
        
        # ETIQUETA CRITICA PARA LA NOCHE: TSF lee 'isdaytime' para cambiar el fondo/luna
        ET.SubElement(curr, "isdaytime").text = "true" if is_day else "false"
        
        forecast = ET.SubElement(root, "forecast")
        for i in range(min(5, len(daily.get('time', [])))):
            day = ET.SubElement(forecast, "day")
            ET.SubElement(day, "obsdate").text = daily.get('time', [])[i]
            ET.SubElement(day, "hightemperature").text = str(c_to_f(daily.get('temperature_2m_max', [])[i]))
            ET.SubElement(day, "lowtemperature").text = str(c_to_f(daily.get('temperature_2m_min', [])[i]))
            # Iconos de pronóstico siempre modo día según estándar AccuWeather
            ET.SubElement(day, "weathericon").text = str(get_accu_icon(daily.get('weather_code', [])[i], True)).zfill(2)
        
        xml_output = '<?xml version="1.0" encoding="utf-8" ?>' + ET.tostring(root, encoding='unicode')
        return Response(xml_output, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

def get_accu_icon(code, is_day=True):
    # Mapa de iconos corregido para la noche
    icons = {0: 1, 1: 2, 2: 3, 3: 6, 45: 11, 51: 12, 61: 13, 63: 15, 80: 18, 95: 16}
    icon = icons.get(code, 1)
    if not is_day:
        # En AccuWeather, los iconos de noche suelen ser a partir del 33
        night_icons = {1: 33, 2: 34, 3: 35, 6: 36}
        return night_icons.get(icon, icon)
    return icon

@app.route('/')
def index(): return "TSF Active"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import traceback

app = Flask(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

def c_to_f(c):
    """Convierte Celsius a Fahrenheit."""
    return (c * 9/5) + 32

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
        resp.raise_for_status()  # ← IMPORTANTE: Verificar errores HTTP
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
        print(traceback.format_exc())
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

        print(f"Consultando clima para: lat={lat}, lon={lon}")  # ← DEBUG

        # ← CORREGIDO: Open-Meteo espera parámetros separados por comas, no listas Python
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 5
        }

        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()  # ← Verificar errores HTTP
        data = resp.json()
        
        print(f"Respuesta Open-Meteo: {data}")  # ← DEBUG

        current = data.get('current', {})
        daily = data.get('daily', {})

        # ← CORREGIDO: Verificar que tenemos datos válidos
        if not current or not daily:
            raise ValueError("Datos incompletos de Open-Meteo")

        is_day = current.get('is_day', 1) == 1

        root = ET.Element("adc_database")

        # Condiciones actuales
        curr_node = ET.SubElement(root, "currentconditions")
        ET.SubElement(curr_node, "weathertext").text = get_weather_text(current.get('weather_code', 0))
        icon_code = get_accu_icon(current.get('weather_code', 0), is_day)
        ET.SubElement(curr_node, "weathericon").text = str(icon_code)

        temp_c = current.get('temperature_2m', 15)
        temp_f = int(c_to_f(temp_c))
        ET.SubElement(curr_node, "temperature").text = str(temp_f)

        ET.SubElement(curr_node, "humidity").text = str(current.get('relative_humidity_2m', 50))
        ET.SubElement(curr_node, "isdaytime").text = "true" if is_day else "false"

        # Pronóstico
        forecast_node = ET.SubElement(root, "forecast")
        
        # ← CORREGIDO: Verificar que daily tiene datos antes de iterar
        daily_times = daily.get('time', [])
        daily_codes = daily.get('weather_code', [])
        daily_max = daily.get('temperature_2m_max', [])
        daily_min = daily.get('temperature_2m_min', [])
        
        if not daily_times:
            raise ValueError("No hay datos diarios disponibles")

        for i in range(min(5, len(daily_times))):
            day_node = ET.SubElement(forecast_node, "day")
            ET.SubElement(day_node, "obsdate").text = daily_times[i]

            # ← CORREGIDO: Verificar índices antes de acceder
            max_c = daily_max[i] if i < len(daily_max) else 15
            min_c = daily_min[i] if i < len(daily_min) else 10
            
            max_f = int(c_to_f(max_c))
            min_f = int(c_to_f(min_c))

            ET.SubElement(day_node, "hightemperature").text = str(max_f)
            ET.SubElement(day_node, "lowtemperature").text = str(min_f)
            
            code = daily_codes[i] if i < len(daily_codes) else 0
            ET.SubElement(day_node, "weathericon").text = str(get_accu_icon(code, True))
            ET.SubElement(day_node, "weathertext").text = get_weather_text(code)

        xml_str = ET.tostring(root, encoding='unicode')
        print(f"XML generado: {xml_str[:200]}...")  # ← DEBUG
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        print(f"ERROR en weather-data: {str(e)}")
        print(traceback.format_exc())
        # XML de fallback para que TSF no se rompa
        fallback = '''<?xml version="1.0"?><adc_database><currentconditions><temperature>60</temperature><weathericon>1</weathericon><weathertext>Error</weathertext></currentconditions></adc_database>'''
        return Response(fallback, mimetype='application/xml')

def get_weather_text(code):
    texts = {
        0: "Despejado", 1: "Mayormente Despejado", 2: "Parcialmente Nublado", 3: "Nublado",
        45: "Niebla", 48: "Niebla con Escarcha", 51: "Llovizna Ligera", 53: "Llovizna",
        55: "Llovizna Intensa", 61: "Lluvia Ligera", 63: "Lluvia", 65: "Lluvia Fuerte",
        71: "Nieve Ligera", 73: "Nieve", 75: "Nieve Fuerte", 77: "Granizo",
        80: "Chubascos Ligeros", 81: "Chubascos", 82: "Chubascos Fuertes",
        95: "Tormenta", 96: "Tormenta con Granizo", 99: "Tormenta Fuerte"
    }
    return texts.get(code, "Despejado")

def get_accu_icon(code, is_day=True):
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

@app.route('/')
def index():
    return "<h1>TSF Weather Server (Proyecto Fénix)</h1><p>Servidor activo y escuchando...</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
        

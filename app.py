from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import os

app = Flask(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# ============================================================
# ENDPOINT 1: Búsqueda de ciudades (Ruta original de TSF Shell)
# ============================================================
@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    
    if not query or len(query) < 2:
        return Response('<?xml version="1.0"?><Locations></Locations>', 
                       mimetype='application/xml')
    
    try:
        params = {
            "name": query,
            "count": 10,
            "language": "es",
            "format": "json"
        }
        
        resp = requests.get(GEOCODING_URL, params=params, timeout=10)
        data = resp.json()
        results = data.get('results', [])
        
        root = ET.Element("Locations")
        
        for city in results:
            loc = ET.SubElement(root, "Location")
            # Generamos una key compatible: lat_lon
            lat = city.get('latitude', 0)
            lon = city.get('longitude', 0)
            key = f"{str(lat).replace('.', '_')}_{str(lon).replace('.', '_')}"
            
            ET.SubElement(loc, "Key").text = key
            ET.SubElement(loc, "LocalizedName").text = city.get('name', 'Unknown')
            ET.SubElement(loc, "EnglishName").text = city.get('name', 'Unknown')
            
            country = ET.SubElement(loc, "Country")
            ET.SubElement(country, "LocalizedName").text = city.get('country', 'Unknown')
            ET.SubElement(country, "ID").text = city.get('country_code', 'XX')
            
            geo = ET.SubElement(loc, "GeoPosition")
            ET.SubElement(geo, "Latitude").text = str(lat)
            ET.SubElement(geo, "Longitude").text = str(lon)
        
        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')
        
    except Exception as e:
        return Response('<?xml version="1.0"?><Locations></Locations>', 
                       mimetype='application/xml')

# ============================================================
# ENDPOINT 2: Datos del clima (Ruta original de TSF Shell)
# ============================================================
@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat = request.args.get('slat')
    lon = request.args.get('slon')
    location_key = request.args.get('location') # A veces usa location key
    
    try:
        if not lat or not lon:
            if location_key and '_' in location_key:
                parts = location_key.split('_')
                lat = float(parts[0] + '.' + parts[1])
                lon = float(parts[2] + '.' + parts[3])
            else:
                # Default a Madrid si no hay datos
                lat, lon = 40.4168, -3.7038
        
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m"],
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto",
            "forecast_days": 5
        }
        
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        data = resp.json()
        current = data.get('current', {})
        daily = data.get('daily', {})
        
        # Construir XML compatible con AccuWeather v1
        root = ET.Element("Weather")
        
        # Condiciones actuales
        curr_node = ET.SubElement(root, "CurrentConditions")
        ET.SubElement(curr_node, "WeatherText").text = get_weather_text(current.get('weather_code', 0))
        ET.SubElement(curr_node, "WeatherIcon").text = str(get_accu_icon(current.get('weather_code', 0)))
        ET.SubElement(curr_node, "Temperature").text = str(int(current.get('temperature_2m', 20)))
        ET.SubElement(curr_node, "Humidity").text = str(current.get('relative_humidity_2m', 50))
        
        # Pronóstico
        forecast_node = ET.SubElement(root, "Forecast")
        for i in range(min(5, len(daily.get('time', [])))):
            day_node = ET.SubElement(forecast_node, "Day")
            ET.SubElement(day_node, "Date").text = daily.get('time', [])[i]
            ET.SubElement(day_node, "HighTemperature").text = str(int(daily.get('temperature_2m_max', [])[i]))
            ET.SubElement(day_node, "LowTemperature").text = str(int(daily.get('temperature_2m_min', [])[i]))
            ET.SubElement(day_node, "WeatherIcon").text = str(get_accu_icon(daily.get('weather_code', [])[i]))
            ET.SubElement(day_node, "WeatherText").text = get_weather_text(daily.get('weather_code', [])[i])
        
        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')
        
    except Exception as e:
        return Response('<?xml version="1.0"?><Weather><Error>Data unavailable</Error></Weather>', 
                       mimetype='application/xml')

# ============================================================
# ENDPOINTS ADICIONALES (Para compatibilidad futura)
# ============================================================
@app.route('/locations/v1/cities/search')
def search_cities():
    return city_find_legacy()

@app.route('/currentconditions/v1/<location_key>')
def current_conditions(location_key):
    # Reutilizamos la lógica de weather_data_legacy
    return weather_data_legacy()

def get_weather_text(code):
    texts = {
        0: "Sunny", 1: "Mostly Sunny", 2: "Partly Cloudy", 3: "Cloudy",
        45: "Foggy", 48: "Foggy", 51: "Light Drizzle", 53: "Drizzle",
        55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
        71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow Grains",
        80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
        95: "Thunderstorm", 96: "Thunderstorm w/ Hail", 99: "Heavy Thunderstorm"
    }
    return texts.get(code, "Unknown")

def get_accu_icon(code):
    icons = {
        0: 1, 1: 2, 2: 3, 3: 4, 45: 11, 48: 11, 51: 12, 53: 12, 55: 12,
        61: 13, 63: 14, 65: 15, 71: 19, 73: 20, 75: 21, 77: 19,
        80: 12, 81: 13, 82: 14, 85: 19, 86: 20, 95: 15, 96: 16, 99: 17
    }
    return icons.get(code, 1)

@app.route('/')
def index():
    return "<h1>TSF Weather Server (Proyecto Fénix)</h1><p>Servidor activo y escuchando...</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

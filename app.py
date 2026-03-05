from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import os

app = Flask(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# ============================================================
# ENDPOINT 1: Búsqueda de ciudades por nombre (AUTOCOMPLETAR)
# ============================================================
@app.route('/locations/v1/cities/search')
def search_cities():
    query = request.args.get('q', '')
    
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
            ET.SubElement(loc, "Key").text = f"{city.get('latitude')}{city.get('longitude')}".replace('.', '')
            ET.SubElement(loc, "LocalizedName").text = city.get('name', 'Unknown')
            ET.SubElement(loc, "EnglishName").text = city.get('name', 'Unknown')
            
            country = ET.SubElement(loc, "Country")
            ET.SubElement(country, "LocalizedName").text = city.get('country', 'Unknown')
            ET.SubElement(country, "ID").text = city.get('country_code', 'XX')
            
            geo = ET.SubElement(loc, "GeoPosition")
            ET.SubElement(geo, "Latitude").text = str(city.get('latitude', 0))
            ET.SubElement(geo, "Longitude").text = str(city.get('longitude', 0))
        
        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')
        
    except Exception as e:
        return Response('<?xml version="1.0"?><Locations></Locations>', 
                       mimetype='application/xml')

# ============================================================
# ENDPOINT 2: Geoposición por coordenadas
# ============================================================
@app.route('/locations/v1/cities/geoposition/search')
def location_by_geo():
    lat = request.args.get('q', '').split(',')[0] if ',' in request.args.get('q', '') else request.args.get('lat')
    lon = request.args.get('q', '').split(',')[1] if ',' in request.args.get('q', '') else request.args.get('lon')
    
    if not lat or not lon:
        return Response('<?xml version="1.0"?><Location></Location>', 
                       mimetype='application/xml')
    
    root = ET.Element("Location")
    ET.SubElement(root, "Key").text = f"{lat}{lon}".replace('.', '')
    ET.SubElement(root, "LocalizedName").text = "Current Location"
    ET.SubElement(root, "EnglishName").text = "Current Location"
    
    country = ET.SubElement(root, "Country")
    ET.SubElement(country, "LocalizedName").text = "Unknown"
    ET.SubElement(country, "ID").text = "XX"
    
    geo = ET.SubElement(root, "GeoPosition")
    ET.SubElement(geo, "Latitude").text = str(lat)
    ET.SubElement(geo, "Longitude").text = str(lon)
    
    xml_str = ET.tostring(root, encoding='unicode')
    return Response(xml_str, mimetype='application/xml')

# ============================================================
# ENDPOINT 3: Condiciones actuales del clima
# ============================================================
@app.route('/currentconditions/v1/<location_key>')
def current_conditions(location_key):
    try:
        if '_' in location_key:
            parts = location_key.split('_')
            lat = float(parts[0] + '.' + parts[1])
            lon = float(parts[2] + '.' + parts[3]) if len(parts) > 3 else 0.0
        else:
            lat, lon = 40.4168, -3.7038
        
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "wind_speed_10m"],
            "timezone": "auto"
        }
        
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        data = resp.json()
        current = data.get('current', {})
        
        root = ET.Element("CurrentConditions")
        
        ET.SubElement(root, "LocalObservationDateTime").text = datetime.now().isoformat()
        ET.SubElement(root, "EpochTime").text = str(int(datetime.now().timestamp()))
        ET.SubElement(root, "WeatherText").text = get_weather_text(current.get('weather_code', 0))
        ET.SubElement(root, "WeatherIcon").text = str(get_accu_icon(current.get('weather_code', 0)))
        ET.SubElement(root, "HasPrecipitation").text = "false"
        ET.SubElement(root, "IsDayTime").text = "true"
        
        temp = ET.SubElement(root, "Temperature")
        metric = ET.SubElement(temp, "Metric")
        ET.SubElement(metric, "Value").text = str(current.get('temperature_2m', 20))
        ET.SubElement(metric, "Unit").text = "C"
        ET.SubElement(metric, "UnitType").text = "17"
        
        imperial = ET.SubElement(temp, "Imperial")
        ET.SubElement(imperial, "Value").text = str(current.get('temperature_2m', 20) * 9/5 + 32)
        ET.SubElement(imperial, "Unit").text = "F"
        ET.SubElement(imperial, "UnitType").text = "18"
        
        ET.SubElement(root, "RelativeHumidity").text = str(current.get('relative_humidity_2m', 50))
        
        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')
        
    except Exception as e:
        root = ET.Element("CurrentConditions")
        ET.SubElement(root, "WeatherText").text = "Sunny"
        ET.SubElement(root, "WeatherIcon").text = "1"
        temp = ET.SubElement(root, "Temperature")
        metric = ET.SubElement(temp, "Metric")
        ET.SubElement(metric, "Value").text = "22"
        ET.SubElement(metric, "Unit").text = "C"
        
        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')

# ============================================================
# ENDPOINT 4: Pronóstico de 5 días
# ============================================================
@app.route('/forecasts/v1/daily/5day/<location_key>')
def forecast_5day(location_key):
    try:
        if '_' in location_key:
            parts = location_key.split('_')
            lat = float(parts[0] + '.' + parts[1])
            lon = float(parts[2] + '.' + parts[3]) if len(parts) > 3 else 0.0
        else:
            lat, lon = 40.4168, -3.7038
        
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto",
            "forecast_days": 5
        }
        
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        data = resp.json()
        daily = data.get('daily', {})
        
        root = ET.Element("DailyForecasts")
        
        for i in range(5):
            try:
                day = ET.SubElement(root, "DailyForecast")
                
                date_str = daily.get('time', [])[i] if i < len(daily.get('time', [])) else ""
                ET.SubElement(day, "Date").text = date_str
                
                temp = ET.SubElement(day, "Temperature")
                min_temp = daily.get('temperature_2m_min', [])[i] if i < len(daily.get('temperature_2m_min', [])) else 15
                max_temp = daily.get('temperature_2m_max', [])[i] if i < len(daily.get('temperature_2m_max', [])) else 25
                
                min_elem = ET.SubElement(temp, "Minimum")
                ET.SubElement(min_elem, "Value").text = str(min_temp)
                ET.SubElement(min_elem, "Unit").text = "C"
                
                max_elem = ET.SubElement(temp, "Maximum")
                ET.SubElement(max_elem, "Value").text = str(max_temp)
                ET.SubElement(max_elem, "Unit").text = "C"
                
                day_elem = ET.SubElement(day, "Day")
                code = daily.get('weather_code', [])[i] if i < len(daily.get('weather_code', [])) else 0
                ET.SubElement(day_elem, "Icon").text = str(get_accu_icon(code))
                ET.SubElement(day_elem, "IconPhrase").text = get_weather_text(code)
                
            except:
                continue
        
        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')
        
    except Exception as e:
        root = ET.Element("DailyForecasts")
        xml_str = ET.tostring(root, encoding='unicode')
        return Response(xml_str, mimetype='application/xml')

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
    return """
    <h1>TSF Weather Server</h1>
    <p>Servidor funcionando correctamente</p>
    <p>Endpoints disponibles:</p>
    <ul>
        <li>/locations/v1/cities/search?q=CIUDAD - Buscar ciudad</li>
        <li>/locations/v1/cities/geoposition/search - Por coordenadas</li>
        <li>/currentconditions/v1/KEY - Clima actual</li>
        <li>/forecasts/v1/daily/5day/KEY - Pronóstico 5 días</li>
    </ul>
    """

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

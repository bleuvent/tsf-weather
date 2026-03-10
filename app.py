from flask import Flask, request, Response
import requests
import os

app = Flask(__name__)

def c_to_f(c):
    return int((c * 9/5) + 32)

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '').replace('+', ' ').strip()
    try:
        # Buscamos la ciudad
        resp = requests.get("https://geocoding-api.open-meteo.com/v1/search", 
                            params={"name": query, "count": 5, "language": "es", "format": "json"}, timeout=10)
        results = resp.json().get('results', [])
        
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        for city in results:
            # Usamos las coordenadas directamente como KEY para que sea "estático"
            # Esto evita que dependamos de la memoria del servidor
            legacy_key = f"{city.get('latitude')},{city.get('longitude')}"
            
            xml += '  <location>\n'
            xml += f'    <city>{city.get("name")}</city>\n'
            xml += f'    <state>{city.get("admin1", "ST")}</state>\n'
            xml += f'    <locationKey>{legacy_key}</locationKey>\n'
            xml += '  </location>\n'
        xml += '</adc_database>'
        return Response(xml, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    # Detectamos si viene de GPS (slat/slon) o de búsqueda (location)
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location')
    
    try:
        # Lógica de coordenadas
        if location_key and ',' in location_key:
            lat, lon = location_key.split(',')
        else:
            lat, lon = lat_raw, lon_raw

        if not lat: lat, lon = -33.44, -70.66

        # Llamada a Open-Meteo (Lo que funcionaba con Fake GPS)
        params = {
            "latitude": lat, "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "is_day"],
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto", "forecast_days": 5
        }
        
        data = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10).json()
        current = data.get('current', {})
        daily = data.get('daily', {})
        is_day = current.get('is_day') == 1
        
        # Reconstruimos el XML que el widget SI entendía
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        xml += '  <currentconditions>\n'
        xml += '    <weathertext>Sunny</weathertext>\n'
        
        # Iconos (con la lógica de luna que funcionaba)
        icons = {0: 1, 1: 2, 2: 3, 3: 6, 45: 11, 51: 12, 61: 13, 80: 18, 95: 16}
        icon_val = icons.get(current.get('weather_code', 0), 1)
        if not is_day and icon_val <= 3: icon_val += 32
        
        xml += f'    <weathericon>{str(icon_val).zfill(2)}</weathericon>\n'
        xml += f'    <temperature>{c_to_f(current.get("temperature_2m", 15))}</temperature>\n'
        xml += f'    <humidity>{int(current.get("relative_humidity_2m", 50))}</humidity>\n'
        xml += f'    <isdaytime>{"true" if is_day else "false"}</isdaytime>\n'
        xml += '  </currentconditions>\n'
        
        xml += '  <forecast>\n'
        for i in range(5):
            xml += '    <day>\n'
            xml += f'      <obsdate>{daily.get("time")[i]}</obsdate>\n'
            xml += f'      <hightemperature>{c_to_f(daily.get("temperature_2m_max")[i])}</hightemperature>\n'
            xml += f'      <lowtemperature>{c_to_f(daily.get("temperature_2m_min")[i])}</lowtemperature>\n'
            xml += f'      <weathericon>01</weathericon>\n'
            xml += '    </day>\n'
        xml += '  </forecast>\n'
        xml += '</adc_database>'
        
        return Response(xml, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/')
def index(): return "TSF Weather Stabilized"

if __name__ == '__main__':
    # Usamos el puerto dinámico de Render para evitar el error de "No open ports"
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

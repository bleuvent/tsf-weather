from flask import Flask, request, Response
import requests
import os

app = Flask(__name__)

location_db = {}

def c_to_f(c):
    try:
        return int((c * 9/5) + 32)
    except:
        return 60

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '').replace('+', ' ').strip()
    try:
        resp = requests.get("https://geocoding-api.open-meteo.com/v1/search", 
                            params={"name": query, "count": 10, "language": "es", "format": "json"}, timeout=10)
        results = resp.json().get('results', [])
        
        # El Namespace xmlns:adc es CRITICO para que TSF Shell no muestre Null
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n'
        xml += '<adc_database xmlns:adc="http://www.accuweather.com">\n'
        for city in results:
            city_id = str(abs(hash(f"{city.get('latitude')}{city.get('longitude')}")) % 100000)
            location_db[city_id] = {"lat": city.get('latitude'), "lon": city.get('longitude')}
            
            xml += '  <location>\n'
            xml += f'    <city>{city.get("name")}</city>\n'
            xml += f'    <state>{city.get("admin1", "ST")}</state>\n'
            xml += f'    <locationKey>{city_id}</locationKey>\n'
            xml += f'    <cityname>{city.get("name")}, {city.get("country_code")}</cityname>\n'
            xml += '  </location>\n'
        xml += '</adc_database>'
        return Response(xml, mimetype='text/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='text/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location')
    
    try:
        lat, lon = None, None
        if location_key and location_key in location_db:
            lat, lon = location_db[location_key]['lat'], location_db[location_key]['lon']
        elif lat_raw and lon_raw:
            lat, lon = float(lat_raw), float(lon_raw)
        
        if lat is None: lat, lon = -33.44, -70.66

        w_resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code", "is_day"],
            "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
            "timezone": "auto", "forecast_days": 5
        }, timeout=10)
        
        data = w_resp.json()
        curr = data.get('current', {})
        daily = data.get('daily', {})
        is_day = curr.get('is_day', 1) == 1

        # Construcción manual con Namespace
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n'
        xml += '<adc_database xmlns:adc="http://www.accuweather.com">\n'
        xml += '  <units><temp>f</temp><dist>m</dist></units>\n'
        xml += '  <currentconditions>\n'
        xml += '    <weathertext>Clear</weathertext>\n'
        
        icon = {0:1, 1:2, 2:3, 3:6, 45:11, 51:12, 61:13, 80:18, 95:16}.get(curr.get('weather_code', 0), 1)
        if not is_day and icon <= 5: icon += 32
        
        xml += f'    <weathericon>{str(icon).zfill(2)}</weathericon>\n'
        xml += f'    <temperature>{c_to_f(curr.get("temperature_2m", 15))}</temperature>\n'
        xml += f'    <humidity>{int(curr.get("relative_humidity_2m", 50))}</humidity>\n'
        xml += f'    <isdaytime>{"true" if is_day else "false"}</isdaytime>\n'
        xml += '    <url>http://www.accuweather.com</url>\n'
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
        
        return Response(xml, mimetype='text/xml')
    except Exception as e:
        # Esto evitará los 50 bytes de error, enviando al menos un XML válido
        return Response(f'<?xml version="1.0"?><adc_database><error>{str(e)}</error></adc_database>', mimetype='text/xml')

@app.route('/')
def index(): return "TSF Active"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

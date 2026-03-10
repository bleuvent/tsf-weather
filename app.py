from flask import Flask, request, Response
import requests
import os

app = Flask(__name__)

# Base de datos temporal para IDs
location_db = {}

def get_f(c):
    return int((c * 9/5) + 32)

@app.route('/widget/androiddoes/city-find.asp')
def city_find():
    q = request.args.get('location', '').replace('+', ' ').strip()
    try:
        r = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=5&language=es&format=json", timeout=10)
        data = r.json().get('results', [])
        
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        for item in data:
            # Generar ID simple
            cid = str(abs(hash(str(item.get('latitude')))) % 10000)
            location_db[cid] = {"lat": item.get('latitude'), "lon": item.get('longitude')}
            
            xml += '<location>\n'
            xml += f'<city>{item.get("name")}</city>\n'
            xml += f'<state>{item.get("admin1", "ST")}</state>\n'
            xml += f'<locationKey>{cid}</locationKey>\n'
            xml += f'<cityname>{item.get("name")}</cityname>\n'
            xml += '</location>\n'
        xml += '</adc_database>'
        return Response(xml, mimetype='text/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='text/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data():
    lat = request.args.get('slat')
    lon = request.args.get('slon')
    lkey = request.args.get('location')

    try:
        # Prioridad a la búsqueda manual
        if lkey in location_db:
            lat = location_db[lkey]['lat']
            lon = location_db[lkey]['lon']
        
        if not lat: lat, lon = -33.44, -70.66

        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,is_day&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto"
        res = requests.get(url, timeout=10).json()
        
        curr = res.get('current', {})
        daily = res.get('daily', {})
        is_day = curr.get('is_day') == 1
        
        # Mapa de iconos simplificado
        code = curr.get('weather_code', 0)
        icon = 1
        if code == 0: icon = 1
        elif code < 3: icon = 2
        elif code < 50: icon = 6
        else: icon = 12
        
        if not is_day and icon < 5: icon += 32

        # XML MANUAL (Sin namespaces complejos para evitar el signo ?)
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n'
        xml += '<adc_database>\n'
        xml += '<units><temp>f</temp><dist>m</dist></units>\n'
        xml += '<currentconditions>\n'
        xml += '<weathertext>Condition</weathertext>\n'
        xml += f'<weathericon>{str(icon).zfill(2)}</weathericon>\n'
        xml += f'<temperature>{get_f(curr.get("temperature_2m", 20))}</temperature>\n'
        xml += f'<humidity>{curr.get("relative_humidity_2m", 50)}</humidity>\n'
        xml += f'<isdaytime>{"true" if is_day else "false"}</isdaytime>\n'
        xml += '</currentconditions>\n'
        xml += '<forecast>\n'
        for i in range(5):
            xml += '<day>\n'
            xml += f'<obsdate>{daily.get("time")[i]}</obsdate>\n'
            xml += f'<hightemperature>{get_f(daily.get("temperature_2m_max")[i])}</hightemperature>\n'
            xml += f'<lowtemperature>{get_f(daily.get("temperature_2m_min")[i])}</lowtemperature>\n'
            xml += '<weathericon>01</weathericon>\n'
            xml += '</day>\n'
        xml += '</forecast>\n'
        xml += '</adc_database>'
        
        return Response(xml, mimetype='text/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='text/xml')

@app.route('/')
def home():
    return "TSF Server Online"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

from flask import Flask, request, Response
import requests
import os

app = Flask(__name__)

def c_to_f(c):
    try:
        return int((c * 9/5) + 32)
    except:
        return 0

@app.route('/widget/androiddoes/city-find.asp')
def city_find():
    q = request.args.get('location', '').replace('+', ' ').strip()
    try:
        # Búsqueda simple
        r = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=5&format=json", timeout=10)
        data = r.json().get('results', [])
        
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        for item in data:
            # Enviamos lat,lon como ID para que no se pierda al reiniciar el servidor
            lkey = f"{item.get('latitude')},{item.get('longitude')}"
            xml += '  <location>\n'
            xml += f'    <city>{item.get("name")}</city>\n'
            xml += f'    <state>{item.get("admin1", "ST")}</state>\n'
            xml += f'    <locationKey>{lkey}</locationKey>\n'
            xml += '  </location>\n'
        xml += '</adc_database>'
        return Response(xml, mimetype='application/xml')
    except:
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data():
    lat = request.args.get('slat')
    lon = request.args.get('slon')
    lkey = request.args.get('location')

    try:
        # Si el widget pide una ciudad de la lista, extraemos lat/lon del ID
        if lkey and ',' in lkey:
            lat, lon = lkey.split(',')
        
        if not lat or not lon:
            lat, lon = -33.44, -70.66 # Santiago por defecto si falla el GPS

        # Llamada a la API (idéntica a la que te funcionó antes)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,is_day&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto"
        res = requests.get(url, timeout=10).json()
        
        curr = res.get('current', {})
        daily = res.get('daily', {})
        is_day = curr.get('is_day') == 1
        
        # Lógica de iconos de AccuWeather (Luna incluida)
        code = curr.get('weather_code', 0)
        icon = {0:1, 1:2, 2:3, 3:6, 45:11, 51:12, 61:13, 80:18, 95:16}.get(code, 1)
        if not is_day and icon <= 5: icon += 32 

        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        xml += '  <currentconditions>\n'
        xml += f'    <weathertext>Sunny</weathertext>\n'
        xml += f'    <weathericon>{str(icon).zfill(2)}</weathericon>\n'
        xml += f'    <temperature>{c_to_f(curr.get("temperature_2m"))}</temperature>\n'
        xml += f'    <humidity>{curr.get("relative_humidity_2m")}</humidity>\n'
        xml += f'    <isdaytime>{"true" if is_day else "false"}</isdaytime>\n'
        xml += '  </currentconditions>\n'
        xml += '  <forecast>\n'
        for i in range(5):
            xml += '    <day>\n'
            xml += f'      <obsdate>{daily.get("time")[i]}</obsdate>\n'
            xml += f'      <hightemperature>{c_to_f(daily.get("temperature_2m_max")[i])}</hightemperature>\n'
            xml += f'      <lowtemperature>{c_to_f(daily.get("temperature_2m_min")[i])}</lowtemperature>\n'
            xml += '      <weathericon>01</weathericon>\n'
            xml += '    </day>\n'
        xml += '  </forecast>\n</adc_database>'
        
        return Response(xml, mimetype='application/xml')
    except:
        # Si algo falla, devolvemos un XML mínimo para que no salga el signo "?"
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/')
def home(): return "TSF Ready"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

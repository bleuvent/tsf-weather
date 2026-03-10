from flask import Flask, request, Response
import requests
import os

app = Flask(__name__)

def c_to_f(c):
    try:
        return int((float(c) * 9/5) + 32)
    except:
        return 60

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data():
    # Recuperamos la lógica simple de slat/slon que funcionaba con Fake GPS
    lat = request.args.get('slat')
    lon = request.args.get('slon')
    
    if not lat or not lon:
        lat, lon = "-33.45", "-70.66"

    try:
        # Llamada directa sin variables complejas
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,is_day&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto"
        r = requests.get(url, timeout=10)
        data = r.json()
        
        curr = data.get('current', {})
        daily = data.get('daily', {})
        is_day = curr.get('is_day') == 1
        
        # Lógica de iconos de AccuWeather (La que te mostraba la luna)
        code = curr.get('weather_code', 0)
        icons = {0:1, 1:2, 2:3, 3:6, 45:11, 51:12, 61:13, 80:18, 95:16}
        icon_val = icons.get(code, 1)
        if not is_day and icon_val <= 3: icon_val += 32 

        # XML LIMPIO (El que el widget aceptaba antes)
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        xml += '  <currentconditions>\n'
        xml += f'    <weathertext>Condition</weathertext>\n'
        xml += f'    <weathericon>{str(icon_val).zfill(2)}</weathericon>\n'
        xml += f'    <temperature>{c_to_f(curr.get("temperature_2m"))}</temperature>\n'
        xml += f'    <humidity>{int(curr.get("relative_humidity_2m", 50))}</humidity>\n'
        xml += f'    <isdaytime>{"true" if is_day else "false"}</isdaytime>\n'
        xml += '  </currentconditions>\n'
        xml += '  <forecast>\n'
        
        # Agregamos 5 días de pronóstico
        for i in range(5):
            xml += '    <day>\n'
            xml += f'      <obsdate>{daily.get("time")[i]}</obsdate>\n'
            xml += f'      <hightemperature>{c_to_f(daily.get("temperature_2m_max")[i])}</hightemperature>\n'
            xml += f'      <lowtemperature>{c_to_f(daily.get("temperature_2m_min")[i])}</lowtemperature>\n'
            xml += '      <weathericon>01</weathericon>\n'
            xml += '    </day>\n'
        xml += '  </forecast>\n</adc_database>'
        
        return Response(xml, mimetype='application/xml')
    except Exception as e:
        # Si falla, devolvemos un XML vacío para que el widget intente de nuevo
        return Response('<?xml version="1.0"?><adc_database></adc_database>', mimetype='application/xml')

@app.route('/widget/androiddoes/city-find.asp')
def city_find():
    # Mantenemos la búsqueda mínima para que no de error 404
    xml = '<?xml version="1.0" encoding="utf-8" ?><adc_database></adc_database>'
    return Response(xml, mimetype='application/xml')

@app.route('/')
def home():
    return "TSF GPS Mode Active"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

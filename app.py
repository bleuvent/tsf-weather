from flask import Flask, request, Response
import requests
import os

app = Flask(__name__)

def c_to_f(c):
    try:
        if c is None: return 60
        return int((float(c) * 9/5) + 32)
    except:
        return 60

@app.route('/widget/androiddoes/city-find.asp')
def city_find():
    q = request.args.get('location', '').replace('+', ' ').strip()
    try:
        r = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=5&format=json", timeout=10)
        data = r.json().get('results', [])
        
        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        if data:
            for item in data:
                lkey = f"{item.get('latitude')},{item.get('longitude')}"
                xml += '  <location>\n'
                xml += f'    <city>{item.get("name", "City")}</city>\n'
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
        if lkey and ',' in lkey:
            lat, lon = lkey.split(',')
        
        if not lat or not lon:
            lat, lon = -33.44, -70.66 

        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,is_day&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto"
        res = requests.get(url, timeout=10).json()
        
        curr = res.get('current', {})
        daily = res.get('daily', {})
        is_day = curr.get('is_day', 1) == 1
        
        code = curr.get('weather_code', 0)
        icons = {0:1, 1:2, 2:3, 3:6, 45:11, 51:12, 61:13, 80:18, 95:16}
        icon_val = icons.get(code, 1)
        if not is_day and icon_val <= 3: icon_val += 32 

        xml = '<?xml version="1.0" encoding="utf-8" ?>\n<adc_database>\n'
        xml += '  <currentconditions>\n'
        xml += '    <weathertext>Sunny</weathertext>\n'
        xml += f'    <weathericon>{str(icon_val).zfill(2)}</weathericon>\n'
        xml += f'    <temperature>{c_to_f(curr.get("temperature_2m"))}</temperature>\n'
        xml += f'    <humidity>{int(curr.get("relative_humidity_2m", 50))}</humidity>\n'
        xml += f'    <isdaytime>{"true" if is_day else "false"}</isdaytime>\n'
        xml += '    <url>http://www.accuweather.com</url>\n'
        xml += '  </currentconditions>\n'
        
        xml += '  <forecast>\n'
        days_time = daily.get('time', [])
        highs = daily.get('temperature_2m_max', [])
        lows = daily.get('temperature_2m_min', [])
        
        for i in range(min(5, len(days_time))):
            xml += '    <day>\n'
            xml += f'      <obsdate>{days_time[i]}</obsdate>\n'
            xml += f'      <hightemperature>{c_to_f(highs[i])}</hightemperature>\n'
            xml += f'      <lowtemperature>{c_to_f(lows[i])}</lowtemperature>\n'
            xml += '      <weathericon>01</weathericon>\n'
            xml += '    </day>\n'
        xml += '  </forecast>\n</adc_database>'
        
        return Response(xml, mimetype='application/xml')
    except Exception:
        # Fallback de emergencia
        return Response('<?xml version="1.0"?><adc_database><currentconditions><temperature>60</temperature><weathericon>01</weathericon><url>http://www.accuweather.com</url></currentconditions></adc_database>', mimetype='application/xml')

@app.route('/')
def home():
    return "TSF Server Online"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

from flask import Flask, request, Response
import requests
from datetime import datetime, timedelta
import os
import time
import random

app = Flask(__name__)

# Configuración
OPENWEATHER_KEY = os.environ.get("OPENWEATHER_KEY", "")  # Necesitas esta API key
GEOCODING_URL = "http://api.openweathermap.org/geo/1.0/direct"
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

weather_cache = {}
CACHE_DURATION = timedelta(minutes=15)  # Cache más corto para datos frescos
LAST_REQUEST_TIME = 0
MIN_REQUEST_INTERVAL = 1.0  # 1 segundo entre requests (seguro para 1M/mes)

def get_cache_key(lat, lon):
    return f"{round(lat, 2)}_{round(lon, 2)}"

def get_cached_weather(lat, lon):
    key = get_cache_key(lat, lon)
    if key in weather_cache:
        data, timestamp = weather_cache[key]
        age = datetime.now() - timestamp
        if age < CACHE_DURATION:
            print(f"CACHE HIT: {key}")
            return data
    return None

def set_cached_weather(lat, lon, data):
    key = get_cache_key(lat, lon)
    weather_cache[key] = (data, datetime.now())

def rate_limit():
    global LAST_REQUEST_TIME
    elapsed = time.time() - LAST_REQUEST_TIME
    if elapsed < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - elapsed + random.uniform(0.1, 0.3)
        time.sleep(sleep_time)
    LAST_REQUEST_TIME = time.time()

def kelvin_to_fahrenheit(k):
    return (k - 273.15) * 9/5 + 32

def kelvin_to_celsius(k):
    return k - 273.15

def openweather_to_accu_icon(icon_code, is_day=True):
    """
    Mapeo de códigos de ícono OpenWeatherMap a números AccuWeather
    OpenWeather usa: 01d, 01n, 02d, 02n, 03d, 03n, 04d, 04n, etc.
    """
    icon_map = {
        '01d': 1,   # Clear sky (day) - Soleado
        '01n': 33,  # Clear sky (night) - Despejado noche
        '02d': 3,   # Few clouds (day) - Parcialmente nublado
        '02n': 35,  # Few clouds (night) - Parcialmente nublado noche
        '03d': 6,   # Scattered clouds (day) - Nublado
        '03n': 38,  # Scattered clouds (night) - Nublado noche
        '04d': 7,   # Broken clouds (day) - Muy nublado
        '04n': 38,  # Broken clouds (night) - Muy nublado noche
        '09d': 12,  # Shower rain (day) - Lluvia
        '09n': 39,  # Shower rain (night) - Lluvia noche
        '10d': 12,  # Rain (day) - Lluvia
        '10n': 39,  # Rain (night) - Lluvia noche
        '11d': 15,  # Thunderstorm (day) - Tormenta
        '11n': 41,  # Thunderstorm (night) - Tormenta noche
        '13d': 22,  # Snow (day) - Nieve
        '13n': 44,  # Snow (night) - Nieve noche
        '50d': 11,  # Mist (day) - Neblina
        '50n': 11,  # Mist (night) - Neblina
    }
    return icon_map.get(icon_code, 1 if is_day else 33)

def openweather_to_text(icon_code):
    """Descripción en español basada en el código de ícono"""
    text_map = {
        '01d': 'Despejado',
        '01n': 'Despejado',
        '02d': 'Parcialmente Nublado',
        '02n': 'Parcialmente Nublado',
        '03d': 'Nublado',
        '03n': 'Nublado',
        '04d': 'Muy Nublado',
        '04n': 'Muy Nublado',
        '09d': 'Lluvia',
        '09n': 'Lluvia',
        '10d': 'Lluvia Moderada',
        '10n': 'Lluvia Moderada',
        '11d': 'Tormenta Eléctrica',
        '11n': 'Tormenta Eléctrica',
        '13d': 'Nieve',
        '13n': 'Nieve',
        '50d': 'Neblina',
        '50n': 'Neblina',
    }
    return text_map.get(icon_code, 'Despejado')

@app.route('/widget/androiddoes/city-find.asp')
def city_find_legacy():
    query = request.args.get('location', '')
    query = query.replace('+', ' ').replace(',', ' ').strip()

    if not query or len(query) < 2:
        xml = '<?xml version="1.0" encoding="UTF-8"?><adc_database></adc_database>'
        return Response(xml, mimetype='application/xml')

    try:
        # Usar geocoding de Open-Meteo (no requiere API key)
        params = {"name": query, "count": 10, "language": "es", "format": "json"}
        resp = requests.get("https://geocoding-api.open-meteo.com/v1/search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])

        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<adc_database>']

        for city in results:
            lat = city.get('latitude', 0)
            lon = city.get('longitude', 0)
            lat_formatted = f"{lat:.6f}"
            lon_formatted = f"{lon:.6f}"
            lat_key = lat_formatted.replace('.', '_')
            lon_key = lon_formatted.replace('.', '_')
            safe_key = f"{lat_key}__{lon_key}"
            
            city_name = city.get("name", "Unknown")
            admin1 = city.get("admin1", "")
            country = city.get("country", "XX")
            state = admin1 if admin1 else country

            xml_parts.append('  <location>')
            xml_parts.append(f'    <City>{city_name}</City>')
            xml_parts.append(f'    <State>{state}</State>')
            xml_parts.append(f'    <Country>{country}</Country>')
            xml_parts.append(f'    <locationKey>{safe_key}</locationKey>')
            xml_parts.append('  </location>')

        xml_parts.append('</adc_database>')
        xml_str = '\n'.join(xml_parts)
        print(f"CITY-FIND: {len(results)} results for '{query}'")
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        print(f"CITY-FIND ERROR: {str(e)}")
        xml = '<?xml version="1.0" encoding="UTF-8"?><adc_database></adc_database>'
        return Response(xml, mimetype='application/xml')

@app.route('/widget/androiddoes/weather-data.asp')
def weather_data_legacy():
    lat_raw = request.args.get('slat')
    lon_raw = request.args.get('slon')
    location_key = request.args.get('location') or request.args.get('locationKey')

    print(f"WEATHER-REQ: slat={lat_raw}, slon={lon_raw}, key={location_key}")

    try:
        lat, lon = None, None

        # Parsear locationKey
        if location_key and location_key not in ['null', '', 'None']:
            key_clean = location_key.strip()
            if '__' in key_clean:
                try:
                    parts = key_clean.split('__')
                    if len(parts) == 2:
                        lat = float(parts[0].replace('_', '.'))
                        lon = float(parts[1].replace('_', '.'))
                except:
                    pass

        # Parsear slat/slon
        if lat is None and lat_raw and lon_raw:
            if lat_raw not in ['null', '0.0', '0', ''] and lon_raw not in ['null', '0.0', '0', '']:
                try:
                    lat = float(lat_raw)
                    lon = float(lon_raw)
                except:
                    pass

        # Default: Santiago
        if lat is None or lon is None:
            lat, lon = -33.4489, -70.6693

        # Verificar cache
        cached_data = get_cached_weather(lat, lon)
        if cached_data:
            return generate_weather_xml(cached_data, lat, lon)

        return fetch_openweather(lat, lon)

    except Exception as e:
        print(f"WEATHER ERROR: {str(e)}")
        return generate_fallback_xml(lat, lon)

def fetch_openweather(lat, lon):
    if not OPENWEATHER_KEY:
        print("ERROR: No OPENWEATHER_KEY configured")
        return generate_fallback_xml(lat, lon)
    
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_KEY,
        "units": "metric",
        "lang": "es"
    }

    for attempt in range(3):
        try:
            rate_limit()
            
            # Current weather
            resp = requests.get(WEATHER_URL, params=params, timeout=10)
            if resp.status_code == 429:
                print(f"Rate limited, attempt {attempt+1}")
                time.sleep(2 * (attempt + 1))
                continue
            
            resp.raise_for_status()
            data = resp.json()
            
            # Forecast (5 days/3 hours)
            forecast_params = params.copy()
            forecast_params["cnt"] = 15  # 5 days, 3-hour steps
            forecast_resp = requests.get(FORECAST_URL, params=forecast_params, timeout=10)
            forecast_data = forecast_resp.json() if forecast_resp.status_code == 200 else {}
            
            combined_data = {
                "current": data,
                "forecast": forecast_data
            }
            
            set_cached_weather(lat, lon, combined_data)
            return generate_weather_xml(combined_data, lat, lon)
            
        except Exception as e:
            print(f"Fetch attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(1)
                continue
            return generate_fallback_xml(lat, lon)

def generate_weather_xml(data, lat, lon):
    try:
        current = data.get('current', {})
        forecast = data.get('forecast', {})
        
        # Extraer datos actuales
        weather_list = current.get('weather', [{}])
        weather_main = weather_list[0] if weather_list else {}
        
        icon_code = weather_main.get('icon', '01d')  # Ej: '02d', '04n'
        description = weather_main.get('description', 'Despejado')
        main_condition = weather_main.get('main', 'Clear')
        
        temp_c = current.get('main', {}).get('temp', 15)
        temp_f = int(kelvin_to_fahrenheit(current.get('main', {}).get('temp', 288.15) + 273.15 if temp_c < 100 else temp_c + 273.15))
        # Fix: OpenWeather ya devuelve Celsius si units=metric
        temp_f = int((temp_c * 9/5) + 32)
        
        humidity = current.get('main', {}).get('humidity', 50)
        is_day = 1 if icon_code.endswith('d') else 0
        
        # Ciudad info
        city = current.get('name', 'Unknown')
        country = current.get('sys', {}).get('country', 'CL')
        
        # Generar locationKey
        lat_formatted = f"{lat:.6f}"
        lon_formatted = f"{lon:.6f}"
        lat_key = lat_formatted.replace('.', '_')
        lon_key = lon_formatted.replace('.', '_')
        safe_key = f"{lat_key}__{lon_key}"
        
        # Mapear ícono y texto
        weather_icon = openweather_to_accu_icon(icon_code, is_day)
        weather_text = openweather_to_text(icon_code)
        obs_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        
        print(f"DEBUG: icon_code={icon_code}, is_day={is_day}, accu_icon={weather_icon}, text={weather_text}, temp={temp_c}°C")
        
        # Construir XML
        xml_parts = []
        xml_parts.append('<?xml version="1.0" encoding="UTF-8"?>')
        xml_parts.append('<adc_database>')
        xml_parts.append('  <CurrentConditions>')
        xml_parts.append(f'    <City>{city}</City>')
        xml_parts.append(f'    <State>{country}</State>')
        xml_parts.append(f'    <Country>{country}</Country>')
        xml_parts.append(f'    <locationKey>{safe_key}</locationKey>')
        xml_parts.append(f'    <Temperature>{temp_f}</Temperature>')
        xml_parts.append(f'    <RealFeelTemperature>{temp_f}</RealFeelTemperature>')
        xml_parts.append(f'    <WeatherIcon>{weather_icon}</WeatherIcon>')
        xml_parts.append(f'    <WeatherText>{weather_text}</WeatherText>')
        xml_parts.append(f'    <RelativeHumidity>{humidity}</RelativeHumidity>')
        xml_parts.append(f'    <IsDayTime>{"true" if is_day else "false"}</IsDayTime>')
        xml_parts.append(f'    <LocalObservationDateTime>{obs_time}</LocalObservationDateTime>')
        xml_parts.append(f'    <Latitude>{lat}</Latitude>')
        xml_parts.append(f'    <Longitude>{lon}</Longitude>')
        xml_parts.append('  </CurrentConditions>')
        
        # Forecast (próximos 5 días aprox)
        xml_parts.append('  <forecast>')
        forecast_list = forecast.get('list', [])
        
        # Agrupar por día (tomar el mediodía de cada día)
        days_processed = []
        for item in forecast_list:
            dt_txt = item.get('dt_txt', '')
            if '12:00:00' in dt_txt or '15:00:00' in dt_txt:
                date_str = dt_txt.split(' ')[0]
                if date_str not in days_processed and len(days_processed) < 5:
                    days_processed.append(date_str)
                    
                    day_main = item.get('main', {})
                    day_weather = item.get('weather', [{}])[0]
                    day_icon = day_weather.get('icon', '01d')
                    
                    max_c = day_main.get('temp_max', temp_c)
                    min_c = day_main.get('temp_min', temp_c)
                    max_f = int((max_c * 9/5) + 32)
                    min_f = int((min_c * 9/5) + 32)
                    
                    day_icon_accu = openweather_to_accu_icon(day_icon, 1)
                    day_text = openweather_to_text(day_icon)
                    
                    xml_parts.append('    <day>')
                    xml_parts.append(f'      <obsdate>{date_str}</obsdate>')
                    xml_parts.append(f'      <hightemperature>{max_f}</hightemperature>')
                    xml_parts.append(f'      <lowtemperature>{min_f}</lowtemperature>')
                    xml_parts.append(f'      <weathericon>{day_icon_accu}</weathericon>')
                    xml_parts.append(f'      <weathertext>{day_text}</weathertext>')
                    xml_parts.append('    </day>')
        
        xml_parts.append('  </forecast>')
        xml_parts.append('</adc_database>')
        
        xml_str = '\n'.join(xml_parts)
        print(f"WEATHER: {len(xml_str)} bytes for {city}, icon={weather_icon} ({icon_code})")
        
        return Response(xml_str, mimetype='application/xml', content_type='application/xml; charset=UTF-8')
        
    except Exception as e:
        print(f"XML GEN ERROR: {e}")
        import traceback
        traceback.print_exc()
        return generate_fallback_xml(lat, lon)

def generate_fallback_xml(lat=-33.4489, lon=-70.6693):
    lat_formatted = f"{lat:.6f}"
    lon_formatted = f"{lon:.6f}"
    lat_key = lat_formatted.replace('.', '_')
    lon_key = lon_formatted.replace('.', '_')
    safe_key = f"{lat_key}__{lon_key}"
    obs_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<adc_database>
  <CurrentConditions>
    <City>Santiago</City>
    <State>CL</State>
    <Country>CL</Country>
    <locationKey>{safe_key}</locationKey>
    <Temperature>65</Temperature>
    <RealFeelTemperature>65</RealFeelTemperature>
    <WeatherIcon>3</WeatherIcon>
    <WeatherText>Servicio No Disponible</WeatherText>
    <RelativeHumidity>50</RelativeHumidity>
    <IsDayTime>true</IsDayTime>
    <LocalObservationDateTime>{obs_time}</LocalObservationDateTime>
    <Latitude>{lat}</Latitude>
    <Longitude>{lon}</Longitude>
  </CurrentConditions>
</adc_database>"""
    
    return Response(xml, mimetype='application/xml', content_type='application/xml; charset=UTF-8')

@app.route('/')
def index():
    return "<h1>TSF Weather Server</h1><p>OpenWeatherMap API Compatible</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    

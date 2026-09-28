from flask import Flask, request, Response
import requests
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/proxy')
def proxy():
    target_url = request.args.get('url')
    if not target_url:
        return "Falta la URL", 400
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://pluto.tv/",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }
    
    try:
        resp = requests.get(target_url, headers=headers, stream=True, timeout=15)
        
        # Filtramos todas las cabeceras de CORS y de control que puedan venir del servidor original
        excluded_headers = [
            'content-encoding', 'content-length', 'transfer-encoding', 'connection',
            'access-control-allow-origin', 'access-control-allow-methods', 'access-control-allow-headers'
        ]
        
        filtered_headers = []
        for name, value in resp.raw.headers.items():
            if name.lower() not in excluded_headers:
                filtered_headers.append((name, value))
                
        # Forzamos una cabecera abierta para que tu GitHub Pages lo acepte sin problemas
        filtered_headers.append(('Access-Control-Allow-Origin', '*'))
        
        return Response(resp.iter_content(chunk_size=2048), 
                        status=resp.status_code, 
                        content_type=resp.headers.get('Content-Type'),
                        headers=filtered_headers)
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

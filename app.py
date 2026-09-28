from flask import Flask, request, Response
import requests
from flask_cors import CORS

app = Flask(__name__)
# Habilita CORS para que tu frontend en GitHub Pages pueda leer la respuesta
CORS(app)

@app.route('/proxy')
def proxy():
    target_url = request.args.get('url')
    if not target_url:
        return "Falta la URL", 400
    
    # Camuflamos la petición simulando ser un navegador de Windows real
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }
    
    try:
        # stream=True permite enviar el video en fragmentos (HLS) sin colapsar la RAM
        resp = requests.get(target_url, headers=headers, stream=True, timeout=15)
        
        # Filtramos encabezados de red que chocan con la retransmisión
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]
        
        return Response(resp.iter_content(chunk_size=2048), 
                        status=resp.status_code, 
                        content_type=resp.headers.get('Content-Type'),
                        headers=headers)
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
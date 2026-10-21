from flask import Flask, jsonify
from flask_cors import CORS
import json
import os

app = Flask(__name__)
CORS(app)

@app.route('/api/noticias', methods=['GET'])
def pegar_noticias():
    try:
        # Busca o arquivo gerado pelo script V2 do seu colega
        caminho_arquivo = os.path.join('data', 'noticias.json')
        
        if not os.path.exists(caminho_arquivo):
            return jsonify([{"erro": "Arquivo não encontrado. Rode o coletar_urls.py primeiro."}]), 404

        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            noticias_brutas = json.load(f)
        
        noticias_formatadas = []
        
        for noticia in noticias_brutas:
            # Mantém a estrutura que o front-end já espera, usando "Geral" 
            # até que seus colegas implementem os filtros específicos.
            noticias_formatadas.append({
                "title": noticia.get('titulo', 'Sem título'),
                "category": "Geral", 
                "summary": noticia.get('descricao', 'Resumo indisponível.'),
                "date": noticia.get('data_publicacao', 'Data recente')[:10],
                "tags": [noticia.get('fonte', 'Fonte Desconhecida')],
                "url": noticia.get('url_original', '#') # Link para a notícia real
            })
            
        return jsonify(noticias_formatadas)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
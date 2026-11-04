from flask import Flask, jsonify
from flask_cors import CORS
import json
import os
import re

app = Flask(__name__)
CORS(app)

# Nome exibido no card de cada categoria
NOMES = {
    "futebol": "Futebol",
    "aquaticos": "Esportes Aquáticos",
    "ciclismo": "Ciclismo",
    "compras": "Equipamentos e Compras",
}


def formatar(noticia, categoria="Geral"):
    return {
        "title": noticia.get('titulo', 'Sem título'),
        "category": categoria,
        "summary": noticia.get('descricao', 'Resumo indisponível.'),
        "date": noticia.get('data_publicacao', 'Data recente')[:10],
        "tags": [noticia.get('fonte', 'Fonte Desconhecida')],
        "url": noticia.get('url_original', '#'),
    }


@app.route('/api/noticias', methods=['GET'])
def pegar_noticias():
    try:
        caminho = os.path.join('data', 'noticias.json')
        if not os.path.exists(caminho):
            return jsonify([{"erro": "Arquivo não encontrado. Rode o coletar_todas.py primeiro."}]), 404
        with open(caminho, 'r', encoding='utf-8') as f:
            brutas = json.load(f)
        return jsonify([formatar(n) for n in brutas])
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route('/api/noticias/<categoria>', methods=['GET'])
def pegar_noticias_categoria(categoria):
    if not re.fullmatch(r'[a-z0-9_-]+', categoria):
        return jsonify([]), 404
    try:
        caminho = os.path.join('data', categoria, 'noticias.json')
        if not os.path.exists(caminho):
            return jsonify([])  # a página mostra "nenhuma notícia encontrada"
        with open(caminho, 'r', encoding='utf-8') as f:
            brutas = json.load(f)
        nome = NOMES.get(categoria, categoria.capitalize())
        return jsonify([formatar(n, nome) for n in brutas])
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == '__main__':
    app.run(port=5000, debug=True)
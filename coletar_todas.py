"""Roda o Radar uma vez para cada categoria do site.

- Cada categoria tem 1 ou mais temas de busca e um filtro de relevância
  (palavras-chave) aplicado ANTES da seleção final, para não entrar notícia
  fora do assunto.
- Resultado: data/noticias.json (geral) e data/<categoria>/noticias.json.
"""
import argparse
import re
import shutil
from pathlib import Path

import coletar_urls as radar

# Guarda a função original uma única vez (o filtro é aplicado por cima dela).
PONTUAR_ORIGINAL = radar.pontuar_relevancia

# slug -> temas de busca + palavras-chave obrigatórias (regex, sem acento).
# palavras = None significa "sem filtro extra" (categoria geral).
CATEGORIAS = {
    "geral": {
        "temas": ["indústria esportiva"],
        "palavras": None,
    },
    "futebol": {
        "temas": ["futebol"],
        "palavras": [r"futebol", r"brasileirao", r"libertadores", r"sul-americana",
                     r"copa do brasil", r"selecao", r"chuteiras?", r"gols?",
                     r"clubes?", r"torcedor\w*", r"estadios?"],
    },
    "aquaticos": {
        "temas": ["esportes aquáticos natação"],
        "palavras": [r"natacao", r"nadad\w+", r"nadar", r"surf\w*", r"piscinas?",
                     r"aquatic\w+", r"polo aquatico", r"saltos? ornamentais",
                     r"nado artistico", r"remo", r"canoagem", r"mergulho", r"maratona aquatica"],
    },
    "ciclismo": {
        "temas": ["ciclismo"],
        "palavras": [r"ciclismo", r"ciclistas?", r"bicicletas?", r"bikes?",
                     r"pedal\w*", r"mountain bike", r"mtb", r"bmx", r"giro d", r"tour de france"],
    },
    "compras": {
        # Vários temas curtos rendem mais candidatas que um tema longo.
        "temas": ["varejo esportivo", "artigos esportivos", "equipamentos esportivos",
                  "loja de esportes"],
        "palavras": [r"varej\w+", r"lojas?", r"e-commerce", r"tenis", r"chuteiras?",
                     r"camisas?", r"uniformes?", r"equipamentos?", r"artigos?",
                     r"vendas?", r"consumidor\w*", r"nike", r"adidas", r"puma",
                     r"centauro", r"decathlon", r"netshoes", r"olympikus"],
    },
}


def ativar_filtro(palavras):
    """Troca a função de relevância por uma versão que também exige palavra-chave."""
    if not palavras:
        radar.pontuar_relevancia = PONTUAR_ORIGINAL
        return
    padrao = re.compile(r"\b(" + "|".join(palavras) + r")\b")

    def pontuar(noticias, tema):
        filtradas, rejeitadas = PONTUAR_ORIGINAL(noticias, tema)
        mantidas = []
        for n in filtradas:
            texto = radar.sem_acentos(
                (n["titulo"] + " " + n.get("descricao", "") + " " + n["texto"][:1500]).lower())
            if padrao.search(texto):
                mantidas.append(n)
            else:
                n["status"] = "rejeitada"
                n["motivo"] = "fora_da_categoria"
                rejeitadas.append(n)
        return mantidas, rejeitadas

    radar.pontuar_relevancia = pontuar


def montar_args(tema, saida, usar_feeds):
    return argparse.Namespace(
        tema=tema,
        dias_atras=0,
        janela_dias=15,       # últimos 15 dias
        limite=20,
        candidatas=40,
        min_caracteres=350,
        workers=3,
        feeds="feeds.txt" if usar_feeds else "sem_feeds.txt",
        saida=str(saida),
        sem_gnews=False,
        sem_bing=False,
        sem_gdelt=True,       # GDELT deu timeout nos testes
    )


def juntar_temas(pasta, pastas_tmp, limite=20):
    """Une os resultados de vários temas: sem URL repetida, melhores primeiro."""
    vistos, todas = set(), []
    for p in pastas_tmp:
        arquivo = p / "noticias.json"
        if not arquivo.exists():
            continue
        for item in radar.json.loads(arquivo.read_text(encoding="utf-8")):
            chave = item.get("url_original") or item.get("url")
            if chave in vistos:
                continue
            vistos.add(chave)
            todas.append(item)
    todas.sort(key=lambda x: x.get("relevancia", 0), reverse=True)
    escolhidas = radar.selecionar_diverso(todas, limite)
    colunas = ["titulo", "url_original", "fonte", "origens", "data_publicacao",
               "relevancia", "tamanho_texto", "descricao", "texto"]
    pasta.mkdir(parents=True, exist_ok=True)
    radar.salvar_json(pasta / "noticias.json", escolhidas)
    radar.salvar_csv(pasta / "noticias.csv", escolhidas, colunas)
    print(f"  -> {len(escolhidas)} notícias após juntar {len(pastas_tmp)} temas")


def main():
    for slug, cfg in CATEGORIAS.items():
        pasta = Path("data") if slug == "geral" else Path("data") / slug
        ativar_filtro(cfg["palavras"])
        usar_feeds = slug == "geral"   # feeds.txt é geral

        if len(cfg["temas"]) == 1:
            radar.executar(montar_args(cfg["temas"][0], pasta, usar_feeds))
            continue

        temporarias = []
        for i, tema in enumerate(cfg["temas"]):
            tmp = pasta / f"_tmp{i}"
            radar.executar(montar_args(tema, tmp, usar_feeds))
            temporarias.append(tmp)
        juntar_temas(pasta, temporarias)
        for tmp in temporarias:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
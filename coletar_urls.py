"""Radar da Indústria Esportiva - coletor e extrator V2.

Coleta candidatos de Google News, Bing News RSS, GDELT e feeds RSS opcionais.
Valida a data de publicação, extrai o texto e ordena por relevância heurística.
Não faz classificação temática nem clustering.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, parse_qs, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

TZ = ZoneInfo("America/Sao_Paulo")
USER_AGENT = "FutureAI-Radar/0.2 (projeto academico; coleta moderada de noticias)"
TRACKING = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.5"}


def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_titulo(titulo: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", sem_acentos(titulo).lower())).strip()


def normalizar_url(url: str) -> str:
    try:
        partes = urlsplit(url.strip())
        if partes.scheme not in ("http", "https") or not partes.hostname:
            return ""
        parametros = [(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
                      if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
        return urlunsplit((partes.scheme.lower(), partes.netloc.lower(),
                           partes.path.rstrip("/") or "/", urlencode(parametros), ""))
    except ValueError:
        return ""


def dominio(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def parse_data(valor: str | None) -> date | None:
    """Aceita datas RFC2822, ISO8601, YYYY-MM-DD e timestamp GDELT.

    Quando existe fuso horário, converte a data para Brasília.
    """
    if not valor:
        return None
    s = str(valor).strip()
    if re.fullmatch(r"\d{8}T\d{6}Z", s):
        dt = datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ).date()
    try:
        dt = parsedate_to_datetime(s)
        if dt:
            return dt.astimezone(TZ).date() if dt.tzinfo else dt.date()
    except (ValueError, TypeError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(TZ).date() if dt.tzinfo else dt.date()
    except ValueError:
        return None


def janela_datas(dias_atras: int, janela_dias: int, hoje: date | None = None) -> tuple[date, date]:
    hoje = hoje or datetime.now(TZ).date()
    ultimo = hoje - timedelta(days=dias_atras)
    primeiro = ultimo - timedelta(days=janela_dias - 1)
    return primeiro, ultimo


def nova_noticia(titulo: str, url: str, origem: str, fonte: str = "",
                 data_publicacao: str = "", descricao: str = "", visto_em: str = "") -> dict:
    return {
        "titulo": html.unescape(re.sub(r"<[^>]+>", " ", titulo or "")).strip(),
        "url": (url or "").strip(),
        "origens": [origem],
        "fonte": fonte or dominio(url),
        "data_informada": data_publicacao or "",
        "descricao": html.unescape(re.sub(r"<[^>]+>", " ", descricao or "")).strip(),
        "visto_em": visto_em or "",  # GDELT: detecção NÃO é publicação
    }


def buscar_google(tema: str, limite: int, dias_necessarios: int) -> list[dict]:
    from gnews import GNews

    gnews = GNews(language="pt-419", country="BR", period=f"{max(7, dias_necessarios)}d",
                  max_results=min(limite, 100))
    saida = []
    for item in gnews.get_news(tema):
        publisher = item.get("publisher") or {}
        fonte = publisher.get("title", "") if isinstance(publisher, dict) else str(publisher)
        saida.append(nova_noticia(item.get("title", ""), item.get("url", ""),
                                  "Google News", fonte, item.get("published date", ""),
                                  item.get("description", "")))
    return saida


def resolver_bing(url: str) -> str:
    partes = urlsplit(url)
    if (partes.hostname or "").endswith("bing.com") and partes.path.endswith("/news/apiclick.aspx"):
        return parse_qs(partes.query).get("url", [url])[0]
    return url


def buscar_bing(tema: str, limite: int) -> list[dict]:
    import feedparser

    resposta = requests.get("https://www.bing.com/news/search",
                            params={"q": tema, "format": "rss"},
                            headers=HEADERS, timeout=(6, 20))
    resposta.raise_for_status()
    feed = feedparser.parse(resposta.content)
    saida = []
    for item in feed.entries[:limite]:
        url = resolver_bing(item.get("link", ""))
        fonte_obj = item.get("source", {})
        fonte = fonte_obj.get("title", "") if isinstance(fonte_obj, dict) else ""
        saida.append(nova_noticia(item.get("title", ""), url, "Bing News RSS",
                                  fonte, item.get("published", ""), item.get("summary", "")))
    return saida


def buscar_gdelt(tema: str, limite: int, inicio: date, fim: date) -> list[dict]:
    # O GDELT usa UTC. 'seendate' indica a detecção, não a publicação.
    dt_inicio = datetime.combine(inicio, time.min, tzinfo=TZ).astimezone(timezone.utc)
    dt_fim = datetime.combine(fim + timedelta(days=1), time.min, tzinfo=TZ).astimezone(timezone.utc)
    consultas = [f'"{tema}"']
    if "esport" in sem_acentos(tema).lower() or "sport" in tema.lower():
        # Expressões amplas, sem pré-classificar tendências ou modalidades.
        consultas += ['"sports industry"', '"sports business"', '"mercado esportivo"']
    resposta = requests.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={"query": "(" + " OR ".join(consultas) + ")", "mode": "ArtList",
                "format": "json", "maxrecords": min(limite, 250), "sort": "DateDesc",
                "startdatetime": dt_inicio.strftime("%Y%m%d%H%M%S"),
                "enddatetime": dt_fim.strftime("%Y%m%d%H%M%S")},
        headers=HEADERS, timeout=(6, 25))
    resposta.raise_for_status()
    conteudo = resposta.json()
    return [nova_noticia(item.get("title", ""), item.get("url", ""),
                         "GDELT", item.get("domain", ""),
                         data_publicacao="", visto_em=item.get("seendate", ""))
            for item in conteudo.get("articles", [])]


def buscar_feeds(caminho: Path, limite_por_feed: int) -> list[dict]:
    import feedparser

    if not caminho.exists():
        return []
    feeds = [l.strip() for l in caminho.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    saida = []
    for url_feed in feeds:
        try:
            resposta = requests.get(url_feed, headers=HEADERS, timeout=(6, 20))
            resposta.raise_for_status()
            feed = feedparser.parse(resposta.content)
            nome = feed.feed.get("title", dominio(url_feed))
            for item in feed.entries[:limite_por_feed]:
                saida.append(nova_noticia(item.get("title", ""), item.get("link", ""),
                                          "RSS direto", nome, item.get("published", "") or
                                          item.get("updated", ""), item.get("summary", "")))
        except Exception as erro:
            print(f"[AVISO] RSS {url_feed}: {erro}")
    return saida


def deduplicar_candidatas(candidatas: list[dict]) -> list[dict]:
    unicas = []
    urls = {}
    titulos = {}
    for item in candidatas:
        url = normalizar_url(item["url"])
        titulo = normalizar_titulo(item["titulo"])
        if not url or not titulo:
            continue
        anterior = urls.get(url) or titulos.get(titulo)
        if anterior is not None:
            for origem in item["origens"]:
                if origem not in anterior["origens"]:
                    anterior["origens"].append(origem)
            # Guarda uma data de publicação quando a fonte anterior não tinha.
            if not anterior["data_informada"] and item["data_informada"]:
                anterior["data_informada"] = item["data_informada"]
            continue
        item["url"] = url
        unicas.append(item)
        urls[url] = item
        titulos[titulo] = item
    return unicas


def resolver_google(url: str) -> str:
    if dominio(url) != "news.google.com":
        return url
    from googlenewsdecoder import gnewsdecoder

    resultado = gnewsdecoder(url, interval=0, timeout=12.0)
    if not resultado.get("success") or not resultado.get("decoded_url"):
        raise RuntimeError(f"Falha ao resolver link do Google News: {resultado.get('message', '')}")
    resolvida = normalizar_url(resultado["decoded_url"])
    if not resolvida or dominio(resolvida) == "news.google.com":
        raise RuntimeError("A URL original não foi encontrada")
    return resolvida


def extrair_noticia(item: dict, inicio: date, fim: date, min_caracteres: int) -> dict:
    """Retorna notícia com status e motivo para auditoria."""
    item = dict(item)
    item["status"] = "rejeitada"
    item["motivo"] = ""
    data_feed = parse_data(item["data_informada"])
    if data_feed and not (inicio <= data_feed <= fim):
        item["motivo"] = "fora_da_janela"
        return item

    try:
        url = resolver_google(item["url"])
        resposta = requests.get(url, headers=HEADERS, timeout=(6, 18), allow_redirects=True)
        resposta.raise_for_status()
        if "html" not in resposta.headers.get("Content-Type", "").lower():
            raise ValueError("URL não retornou HTML")
        if len(resposta.content) > 5_000_000:
            raise ValueError("Página HTML acima de 5 MB")
        url_final = normalizar_url(resposta.url)
        if dominio(url_final) == "news.google.com":
            raise ValueError("Não foi possível chegar ao portal original")

        from trafilatura import bare_extraction
        documento = bare_extraction(resposta.text, url=url_final,
                                    include_comments=False, include_tables=False)
        texto = (getattr(documento, "text", None) or "").strip()
        texto = "\n".join(linha.strip() for linha in texto.splitlines() if linha.strip())
        if len(texto) < min_caracteres:
            raise ValueError(f"Texto muito curto ({len(texto)} caracteres)")

        # Metadados da página complementam a data do feed. A detecção do GDELT não substitui publicação.
        data_pagina = parse_data(getattr(documento, "date", None))
        data_pub = data_feed or data_pagina
        if data_pub is None:
            item["motivo"] = "data_publicacao_nao_confirmada"
            return item
        if not (inicio <= data_pub <= fim):
            item["motivo"] = "fora_da_janela"
            return item

        item.update({
            "url_original": url_final,
            "titulo": (getattr(documento, "title", None) or item["titulo"]).strip(),
            "data_publicacao": data_pub.isoformat(),
            "texto": texto,
            "tamanho_texto": len(texto),
            "status": "aprovada",
            "motivo": "",
        })
        return item
    except Exception as erro:
        item["motivo"] = f"falha_extracao: {str(erro)[:180]}"
        return item


def remover_duplicadas_texto(noticias: list[dict], limiar: float = 0.94) -> tuple[list[dict], list[dict]]:
    if len(noticias) < 2:
        return noticias, []
    # Detecta releases republicados com títulos/URLs diferentes.
    corpus = [item["texto"][:6000] for item in noticias]
    matriz = TfidfVectorizer(strip_accents="unicode", ngram_range=(1, 2),
                             max_features=20000).fit_transform(corpus)
    similares = cosine_similarity(matriz)
    mantidas, removidas, indices = [], [], []
    for i, item in enumerate(noticias):
        anterior = next((j for j in indices if similares[i, j] >= limiar), None)
        if anterior is not None:
            item["status"] = "rejeitada"
            item["motivo"] = "texto_duplicado"
            removidas.append(item)
        else:
            mantidas.append(item)
            indices.append(i)
    return mantidas, removidas


def pontuar_relevancia(noticias: list[dict], tema: str) -> tuple[list[dict], list[dict]]:
    if not noticias:
        return [], []
    titulos = [n["titulo"] for n in noticias]
    contextos = [(n["descricao"] + " " + n["texto"][:1200]).strip() for n in noticias]
    n = len(noticias)
    vetor = TfidfVectorizer(analyzer="char", ngram_range=(3, 5),
                            strip_accents="unicode", max_features=30000)
    matriz = vetor.fit_transform([tema] + titulos + contextos)
    similar_titulo = cosine_similarity(matriz[0:1], matriz[1:n + 1]).ravel()
    similar_contexto = cosine_similarity(matriz[0:1], matriz[n + 1:]).ravel()
    filtradas, rejeitadas = [], []
    tema_normal = sem_acentos(tema).lower()
    tema_esporte = "esport" in tema_normal or "sport" in tema_normal
    for i, item in enumerate(noticias):
        # Apenas filtro amplo de domínio, NÃO classificação por modalidade/tendência.
        conjunto = sem_acentos((item["titulo"] + " " + item["descricao"] + " " +
                                item["texto"][:2000]).lower())
        if tema_esporte and not re.search(r"\b(esport\w*|sport\w*|atlet\w*|olimpi\w*)\b", conjunto):
            item["status"] = "rejeitada"
            item["motivo"] = "sem_contexto_esportivo"
            rejeitadas.append(item)
            continue
        qualidade = min(1.0, item["tamanho_texto"] / 2200)
        # Heurística transparente: não é probabilidade de relevância.
        nota = 100 * (0.60 * float(similar_titulo[i]) +
                      0.30 * float(similar_contexto[i]) + 0.10 * qualidade)
        item["relevancia"] = round(nota, 2)
        filtradas.append(item)
    return sorted(filtradas, key=lambda x: x["relevancia"], reverse=True), rejeitadas


def selecionar_diverso(ordenadas: list[dict], limite: int) -> list[dict]:
    if not ordenadas:
        return []
    teto_fonte = max(2, math.ceil(limite / 4))
    escolhidas = []
    contagem = Counter()
    for item in ordenadas:
        dominio_fonte = dominio(item.get("url_original", item["url"]))
        if contagem[dominio_fonte] < teto_fonte:
            escolhidas.append(item)
            contagem[dominio_fonte] += 1
        if len(escolhidas) >= limite:
            return escolhidas
    # Se houver poucas fontes, preenche com o restante, sem fabricar resultados.
    for item in ordenadas:
        if item not in escolhidas:
            escolhidas.append(item)
        if len(escolhidas) >= limite:
            break
    return escolhidas


def salvar_json(caminho: Path, dados: object) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def salvar_csv(caminho: Path, dados: list[dict], colunas: list[str]) -> None:
    with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        for item in dados:
            linha = dict(item)
            linha["origens"] = ", ".join(item.get("origens", []))
            escritor.writerow(linha)


def executar(args: argparse.Namespace) -> None:
    inicio, fim = janela_datas(args.dias_atras, args.janela_dias)
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    print(f"\nFutureAI Radar V2 | Tema: {args.tema}")
    print(f"Janela de publicação (Brasília): {inicio} até {fim}")
    print(f"Meta: {args.limite} notícias | Candidatas por fonte: {args.candidatas}")

    erros_fontes = {}
    candidatas = []
    fontes = []
    if not args.sem_gnews:
        fontes.append(("Google News", lambda: buscar_google(args.tema, args.candidatas,
                           args.dias_atras + args.janela_dias + 3)))
    if not args.sem_bing:
        fontes.append(("Bing News RSS", lambda: buscar_bing(args.tema, args.candidatas)))
    if not args.sem_gdelt:
        fontes.append(("GDELT", lambda: buscar_gdelt(args.tema, args.candidatas, inicio, fim)))
    if Path(args.feeds).exists():
        fontes.append(("RSS direto", lambda: buscar_feeds(Path(args.feeds), args.candidatas)))

    for nome, funcao in fontes:
        try:
            encontrados = funcao()
            print(f"  {nome}: {len(encontrados)} candidatos")
            candidatas.extend(encontrados)
        except Exception as erro:
            erros_fontes[nome] = str(erro)
            print(f"  [AVISO] {nome} indisponível: {erro}")

    candidatas = deduplicar_candidatas(candidatas)
    salvar_json(pasta / "candidatas.json", candidatas)
    print(f"Candidatas únicas: {len(candidatas)}. Extraindo artigos...")

    processadas = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(extrair_noticia, item, inicio, fim, args.min_caracteres)
                   for item in candidatas]
        for i, future in enumerate(as_completed(futures), 1):
            processadas.append(future.result())
            if i % 10 == 0 or i == len(futures):
                print(f"  Processadas: {i}/{len(futures)}")

    aprovadas = [n for n in processadas if n["status"] == "aprovada"]
    rejeitadas = [n for n in processadas if n["status"] != "aprovada"]
    aprovadas, duplicadas = remover_duplicadas_texto(aprovadas)
    rejeitadas.extend(duplicadas)
    aprovadas, fora_tema = pontuar_relevancia(aprovadas, args.tema)
    rejeitadas.extend(fora_tema)
    selecionadas = selecionar_diverso(aprovadas, args.limite)

    colunas = ["titulo", "url_original", "fonte", "origens", "data_publicacao",
               "relevancia", "tamanho_texto", "descricao", "texto"]
    salvar_json(pasta / "noticias.json", selecionadas)
    salvar_csv(pasta / "noticias.csv", selecionadas, colunas)
    salvar_csv(pasta / "rejeitadas.csv", rejeitadas,
               ["titulo", "url", "origens", "fonte", "data_informada", "status", "motivo"])
    relatorio = {
        "tema": args.tema, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        "candidatas_unicas": len(candidatas), "extraidas_na_janela": len(processadas) -
        sum(1 for n in processadas if n["status"] != "aprovada"),
        "aprovadas_apos_filtros": len(aprovadas), "selecionadas": len(selecionadas),
        "rejeicoes_por_motivo": dict(Counter(n["motivo"].split(":")[0] for n in rejeitadas)),
        "origens_selecionadas": dict(Counter(origem for n in selecionadas for origem in n["origens"])),
        "erros_fontes": erros_fontes,
        "gerado_em": datetime.now(TZ).isoformat(),
    }
    salvar_json(pasta / "relatorio.json", relatorio)
    print(f"\nResultado: {len(selecionadas)} notícias selecionadas")
    print(f"Arquivos em {pasta.resolve()}: noticias.csv, noticias.json, candidatas.json, rejeitadas.csv, relatorio.json")
    if len(selecionadas) < args.limite:
        print("[ATENÇÃO] A meta não foi atingida: faltaram notícias com data/texto válidos na janela.")


def argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FutureAI Radar: coleta multifuente, extração e relevância")
    p.add_argument("--tema", default="indústria esportiva", help="Consulta ampla, sem categorias fixas")
    p.add_argument("--dias-atras", type=int, default=2,
                   help="0=hoje, 1=ontem, 2=anteontem (D-2); padrão: 2")
    p.add_argument("--janela-dias", type=int, default=1,
                   help="Quantidade de dias corridos até --dias-atras, inclusive")
    p.add_argument("--limite", type=int, default=20, help="Máximo de notícias finais")
    p.add_argument("--candidatas", type=int, default=40, help="Máximo de candidatas por fonte")
    p.add_argument("--min-caracteres", type=int, default=350)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--feeds", default="feeds.txt", help="Arquivo opcional de RSS diretos")
    p.add_argument("--saida", default="data", help="Diretório de saída")
    p.add_argument("--sem-gnews", action="store_true")
    p.add_argument("--sem-bing", action="store_true")
    p.add_argument("--sem-gdelt", action="store_true")
    args = p.parse_args()
    if args.dias_atras < 0 or args.janela_dias < 1 or args.limite < 1 or args.candidatas < 1 or args.workers < 1:
        p.error("dias-atras >= 0; janela-dias, limite, candidatas e workers >= 1")
    return args


if __name__ == "__main__":
    executar(argumentos())
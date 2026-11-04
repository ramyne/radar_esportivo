# Radar Esportivo V2.0 🎯

Este é o nosso painel de Inteligência Competitiva focado na Indústria Esportiva. A aplicação utiliza um backend em Python (Flask) para ler dados coletados automaticamente e um frontend em HTML/CSS/JS com layout em Dark Mode.

## 🚀 Como rodar o projeto na sua máquina

1. Certifique-se de ter o Python instalado.
2. Abra o terminal na pasta do projeto, crie o ambiente virtual e instale as dependências:
   ```bash
   python -m venv venv
   source venv/Scripts/activate      # Git Bash (Windows)
   # venv\Scripts\activate           # PowerShell / CMD (Windows)
   pip install -r requirements.txt
   ```
3. **Colete as notícias** (leva alguns minutos). A pasta `data/` não vai no repositório, ela é gerada por este comando:
   ```bash
   python coletar_todas.py
   ```
4. Inicie o servidor da API e deixe a janela aberta:
   ```bash
   python app.py
   ```
5. Abra o arquivo `index.html` no seu navegador.

> Se abrir `127.0.0.1:5000` e aparecer "Not Found", é normal: o `app.py` é só a API. O site é o `index.html`.
> Se as páginas mostrarem "Nenhuma notícia encontrada", rode o passo 3 e recarregue.

---

## 🔄 Atualizando as notícias

Para buscar notícias novas, rode `python coletar_todas.py` de novo e recarregue a página.

No Windows dá para automatizar: o `atualizar.bat` roda a coleta e registra o resultado em `coleta.log`. Para agendar todo dia às 7h, abra o **PowerShell** e rode (ajuste o caminho):

```powershell
schtasks /create /tn "RadarEsportivo" /tr "C:\caminho\do\projeto\atualizar.bat" /sc daily /st 07:00
```

---

## 🧠 Como funciona agora

O `coletar_todas.py` roda o coletor (`coletar_urls.py`) **uma vez para cada categoria**: Geral, Futebol, Esportes Aquáticos, Ciclismo e Compras. Cada uma tem seus próprios temas de busca e palavras-chave de relevância, definidos no topo do arquivo (dicionário `CATEGORIAS`). O resultado de cada categoria fica em `data/<categoria>/noticias.json`.

O `app.py` expõe os dados em duas rotas:

- `/api/noticias`: notícias da categoria geral (página inicial).
- `/api/noticias/<categoria>`: notícias de uma categoria (`futebol`, `aquaticos`, `ciclismo`, `compras`).

Como a API já entrega só o tema de cada página, **não é mais preciso filtrar no front-end**. Cada página só chama a rota da própria categoria.

---

## 🛠️ Como adicionar uma nova página/categoria

1. No `coletar_todas.py`, inclua a categoria no dicionário `CATEGORIAS` com os `temas` de busca e as `palavras` que a notícia precisa ter.
2. No `app.py`, acrescente o nome de exibição no dicionário `NOMES`.
3. Na pasta `paginas/`, copie uma página existente (ex: `ciclismo.html`) e troque o título e a URL do `fetch` para `http://localhost:5000/api/noticias/<categoria>`.
4. No menu superior (tag `<nav>`), coloque `class="ativo"` no link da nova página e acrescente o link nas outras páginas.
5. Rode `python coletar_todas.py` para gerar os dados da nova categoria.

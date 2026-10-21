# Radar Esportivo V2.0 🎯

Este é o nosso painel de Inteligência Competitiva focado na Indústria Esportiva. A aplicação utiliza um backend em Python (Flask) para ler dados coletados automaticamente e um frontend em HTML/CSS/JS com layout em Dark Mode.

## 🚀 Como rodar o projeto na sua máquina

1. Certifique-se de ter o Python instalado.
2. Abra o terminal na pasta do projeto e instale as dependências:
   \`pip install -r requirements.txt\`
3. Inicie o servidor da API:
   \`python app.py\`
4. Abra o arquivo \`index.html\` no seu navegador.

---

## 🛠️ Tarefas da Equipe (O que cada um deve fazer)

Nossa arquitetura está pronta e o layout principal foi definido no \`index.html\` e \`style.css\`. 
A missão agora é criar as páginas específicas de cada tema utilizando a abordagem de **Filtro no Front-end**.

### Passo a passo para a sua página:
1. Vá até a pasta \`paginas/\` e crie o seu arquivo HTML (ex: \`futebol.html\`, \`ciclismo.html\`).
2. Copie todo o código do \`index.html\` principal e cole no seu novo arquivo.
3. No menu superior (tag \`<nav>\`), mude a classe \`class="ativo"\` para o link da sua respectiva página, para que o botão fique verde quando o usuário clicar.
4. **O Filtro Mágico:** Role até o final do seu arquivo, na tag \`<script>\`. Encontre o momento onde o código diz \`const noticias = await resposta.json();\`.
5. Logo abaixo dessa linha, você deve filtrar o array para mostrar apenas o seu tema. Exemplo para a página de Ciclismo:
   \`\`\`javascript
   const noticiasFiltradas = noticias.filter(noticia => 
       noticia.title.toLowerCase().includes("ciclismo") || 
       noticia.title.toLowerCase().includes("bicicleta")
   );
   \`\`\`
6. Altere o \`forEach\` que desenha os cards para usar o seu \`noticiasFiltradas\` em vez de \`noticias\`.

Bom trabalho, squad! 🚀
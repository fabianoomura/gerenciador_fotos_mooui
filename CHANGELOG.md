# Changelog

Todas as mudanças relevantes da versão pública são registradas neste arquivo.

## 0.3.0 — 2026-07-21

### Adicionado

- dicionário de sinônimos de produto (tabela `sinonimos`, curável): buscas por
  "luminária" encontram "abajur", "duvet" encontra "edredom", "porta-treco"/
  "cesto" encontram "caixa organizadora", "cabana" encontra "tenda" etc.;
- expansão da consulta textual com esses sinônimos no ramo FTS.

### Corrigido

- pool de candidatos da busca híbrida: quando a consulta não inferia nenhum
  filtro, o sistema ranqueava um lote arbitrário de fotos e perdia itens que
  casavam pelo nome no caminho. Agora as próprias correspondências de texto
  (FTS, ordenado por bm25) e de vetor formam o pool, respeitando os filtros —
  isso destrava dezenas de milhares de fotos cujo nome de item só existia no
  caminho (ex.: 2.719 "almofada", 631 "organizador"), não na categoria.

## 0.2.0 — 2026-07-16

### Adicionado

- colunas `largura`, `altura`, `orientacao` (vertical/horizontal/square) calculadas
  pelo cabeçalho da imagem com Pillow durante a indexação;
- colunas `possui_pessoa` (tri-estado, só com evidência) e `direitos_uso_status`/
  `direitos_uso_ref` (revisão humana, nunca inferidos; padrão `unknown`);
- filtros novos em `/busca`: `colecao`, `ambiente_tipo`, `ambiente_tema`,
  `drop_tema`, `orientacao`, `possui_pessoa`, `possui_modelo`,
  `direitos_uso_status`;
- filtros negativos com prefixo `!` (ex.: `pessoa_tipo=!modelo`);
- `GET /capabilities` descrevendo o contrato para agentes/integrações;
- `applied_filters`/`ignored_filters` no retorno de `/busca`;
- parâmetros desconhecidos agora retornam 422 em vez de serem ignorados;
- `scripts/backfill_dimensions.py` para preencher dimensões no acervo existente;
- filtro de orientação e dimensões no modal da interface.

### Semântica

- valores repetidos do mesmo filtro combinam com OR; filtros diferentes, com AND;
- filtros restringem os candidatos antes do ranking FTS/vetorial;
- `possui_modelo=true` equivale exatamente a `pessoa_tipo=modelo`.

## 0.1.0 — 2026-07-15

### Adicionado

- indexação incremental de metadados em SQLite;
- FTS5 e busca semântica com embeddings CLIP;
- busca por similaridade e por imagem de referência;
- extração de paletas e agrupamento em famílias de cores;
- API FastAPI somente leitura;
- interface Next.js responsiva com filtros e paginação;
- cache externo de thumbnails;
- proxy Next.js com token mantido no servidor;
- scripts configuráveis para operação em Windows/WSL.

### Segurança da versão pública

- removidos caminhos, endereços de rede e nomes reais do ambiente de origem;
- substituídos exemplos por dados fictícios;
- removidos ativos oficiais de marca e metadados de edição;
- adicionados exemplos de configuração sem credenciais.

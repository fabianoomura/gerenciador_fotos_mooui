-- Schema do banco do catálogo visual.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS imagens (
    id              INTEGER PRIMARY KEY,
    path            TEXT NOT NULL UNIQUE,
    path_raw        TEXT NOT NULL,
    nome_arquivo    TEXT NOT NULL,
    ano             INTEGER,
    tipo            TEXT,               -- ensaio | produtos | quartinhos | arquitetos | (v1.1: tematica)
    colecao         TEXT,
    categoria       TEXT,               -- subcategoria livre dentro do tipo
    drop_numero     INTEGER,
    drop_tema       TEXT,
    pessoa          TEXT,
    pessoa_tipo     TEXT,               -- arquiteto | influenciador | modelo | fotografo | parceiro
    formato_foto    TEXT,               -- ex.: marketplace internacional (nao e origem da pessoa)
    variante        TEXT,               -- ex.: crop
    ambiente_tipo   TEXT,               -- "quarto" | "quarto infantil" (prefixo canonico)
    ambiente_tema   TEXT,               -- "nina e thomas > thomas" | "cachorrinhos" (tema, aninhado com " > ")
    slug_arquivo    TEXT,
    paleta_json     TEXT,
    cores_comerciais_json TEXT,         -- cores simples para site/Google: Verde, Branco...
    cores_marketing_json TEXT,           -- tons mais refinados para busca criativa do marketing
    visual_status   TEXT NOT NULL DEFAULT 'pendente'
                    CHECK (visual_status IN ('pendente', 'ok', 'erro')),
    visual_erro     TEXT,
    reduzida_path   TEXT,
    thumb_path      TEXT,               -- thumbnail gerada fora do share quando nao ha REDUZIDA
    mtime           REAL NOT NULL,
    tamanho_bytes   INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ok'
                    CHECK (status IN ('ok', 'parcial', 'nao_classificado', 'erro', 'removido')),
    criado_em       REAL NOT NULL DEFAULT (unixepoch('subsec')),
    atualizado_em   REAL NOT NULL DEFAULT (unixepoch('subsec'))
);

CREATE INDEX IF NOT EXISTS idx_imagens_ano       ON imagens(ano);
CREATE INDEX IF NOT EXISTS idx_imagens_tipo      ON imagens(tipo);
CREATE INDEX IF NOT EXISTS idx_imagens_colecao   ON imagens(colecao);
CREATE INDEX IF NOT EXISTS idx_imagens_categoria ON imagens(categoria);
CREATE INDEX IF NOT EXISTS idx_imagens_pessoa    ON imagens(pessoa);
CREATE INDEX IF NOT EXISTS idx_imagens_pessoa_tipo ON imagens(pessoa_tipo);
CREATE INDEX IF NOT EXISTS idx_imagens_formato_foto ON imagens(formato_foto);
CREATE INDEX IF NOT EXISTS idx_imagens_variante ON imagens(variante);
CREATE INDEX IF NOT EXISTS idx_imagens_status    ON imagens(status);
CREATE INDEX IF NOT EXISTS idx_imagens_mtime     ON imagens(mtime);
CREATE INDEX IF NOT EXISTS idx_imagens_visual_status ON imagens(visual_status);

-- Full-text search sobre path_raw + slug + pessoa + ambiente (busca textual PT-BR)
CREATE VIRTUAL TABLE IF NOT EXISTS imagens_fts USING fts5(
    path_raw,
    slug_arquivo,
    pessoa,
    ambiente_tipo,
    ambiente_tema,
    colecao,
    categoria,
    drop_tema,
    content='imagens',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS imagens_ai AFTER INSERT ON imagens BEGIN
    INSERT INTO imagens_fts(rowid, path_raw, slug_arquivo, pessoa, ambiente_tipo, ambiente_tema, colecao, categoria, drop_tema)
    VALUES (new.id, new.path_raw, new.slug_arquivo, new.pessoa, new.ambiente_tipo, new.ambiente_tema, new.colecao, new.categoria, new.drop_tema);
END;

CREATE TRIGGER IF NOT EXISTS imagens_ad AFTER DELETE ON imagens BEGIN
    INSERT INTO imagens_fts(imagens_fts, rowid, path_raw, slug_arquivo, pessoa, ambiente_tipo, ambiente_tema, colecao, categoria, drop_tema)
    VALUES ('delete', old.id, old.path_raw, old.slug_arquivo, old.pessoa, old.ambiente_tipo, old.ambiente_tema, old.colecao, old.categoria, old.drop_tema);
END;

CREATE TRIGGER IF NOT EXISTS imagens_au AFTER UPDATE ON imagens BEGIN
    INSERT INTO imagens_fts(imagens_fts, rowid, path_raw, slug_arquivo, pessoa, ambiente_tipo, ambiente_tema, colecao, categoria, drop_tema)
    VALUES ('delete', old.id, old.path_raw, old.slug_arquivo, old.pessoa, old.ambiente_tipo, old.ambiente_tema, old.colecao, old.categoria, old.drop_tema);
    INSERT INTO imagens_fts(rowid, path_raw, slug_arquivo, pessoa, ambiente_tipo, ambiente_tema, colecao, categoria, drop_tema)
    VALUES (new.id, new.path_raw, new.slug_arquivo, new.pessoa, new.ambiente_tipo, new.ambiente_tema, new.colecao, new.categoria, new.drop_tema);
END;

-- Embeddings CLIP em tabela virtual sqlite-vec (carregada em runtime).
-- Ver src/catalogo/db.py: a extensao sqlite-vec e' carregada antes deste CREATE.
-- Dimensao 512 = clip-ViT-B-32-multilingual-v1 (config.chave='modelo').
CREATE VIRTUAL TABLE IF NOT EXISTS vec_imagens USING vec0(
    embedding float[512]
);

-- Vocabulario de tipos (segmento de pasta -> tipo canonico)
CREATE TABLE IF NOT EXISTS vocab_tipo (
    termo   TEXT PRIMARY KEY,   -- ja normalizado (unidecode + lowercase)
    tipo    TEXT NOT NULL       -- ensaio | produtos | quartinhos | arquitetos | tematica
);

-- Vocabulario de pessoas (arquitetos/modelos/parceiros); alimentado pelo indexador
-- e revisavel pelo administrador. Termo ja normalizado.
CREATE TABLE IF NOT EXISTS vocab_pessoas (
    termo       TEXT PRIMARY KEY,
    canonical   TEXT,            -- forma preferida para exibir (ex.: "Pessoa Exemplo")
    pessoa_tipo TEXT,             -- papel revisavel; nunca inferir sem evidencia no path/vocab
    revisado    INTEGER NOT NULL DEFAULT 0 CHECK (revisado IN (0, 1))
);

-- Configuracao chave/valor. Valores JSON quando estruturados.
CREATE TABLE IF NOT EXISTS config (
    chave   TEXT PRIMARY KEY,
    valor   TEXT NOT NULL,
    tipo    TEXT NOT NULL DEFAULT 'string'
            CHECK (tipo IN ('string', 'int', 'float', 'json', 'bool')),
    descricao TEXT
);

-- Fila de segmentos nao classificados para revisao / expansao do vocabulario.
CREATE TABLE IF NOT EXISTS nao_classificados (
    id                  INTEGER PRIMARY KEY,
    imagem_id           INTEGER NOT NULL REFERENCES imagens(id) ON DELETE CASCADE,
    segmento_pendente   TEXT NOT NULL,
    posicao             INTEGER,          -- indice do segmento no path (0-based apos raiz)
    criado_em           REAL NOT NULL DEFAULT (unixepoch('subsec'))
);

CREATE INDEX IF NOT EXISTS idx_nao_class_segmento ON nao_classificados(segmento_pendente);
CREATE INDEX IF NOT EXISTS idx_nao_class_imagem   ON nao_classificados(imagem_id);

-- Historico de execucoes do scan (Prefect flow ou execucao manual)
CREATE TABLE IF NOT EXISTS scan_runs (
    id                      INTEGER PRIMARY KEY,
    inicio                  REAL NOT NULL,
    fim                     REAL,
    novos                   INTEGER NOT NULL DEFAULT 0,
    alterados               INTEGER NOT NULL DEFAULT 0,
    removidos               INTEGER NOT NULL DEFAULT 0,
    ignorados_nao_imagem    INTEGER NOT NULL DEFAULT 0,
    erros                   INTEGER NOT NULL DEFAULT 0,
    escopo_json             TEXT,        -- lista de pastas varridas nesta run
    observacoes             TEXT
);

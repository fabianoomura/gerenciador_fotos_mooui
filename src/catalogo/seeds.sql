-- Seeds iniciais do catalogo.db
-- Configuracao e vocabulario ficam em tabelas para permitir ajustes por instalacao.
-- Todos os termos de vocab ja normalizados (unidecode + lowercase).

-- ============================================================================
-- vocab_tipo: mapeia segmento de pasta -> tipo canonico da imagem
-- ============================================================================
INSERT OR IGNORE INTO vocab_tipo (termo, tipo) VALUES
    ('ensaios',      'ensaio'),
    ('ensaio',       'ensaio'),
    ('produtos',     'produtos'),
    ('produto',      'produtos'),
    ('quartinhos',   'quartinhos'),
    ('quartinho',    'quartinhos'),
    ('arquitetos',   'arquitetos'),
    ('arquiteto',    'arquitetos'),
    ('influenciadores', 'influenciadores'),
    ('influenciador',   'influenciadores');

-- 06/10/2026: pastas de colecao que existiam no acervo sem tipo (pedido do dono).
INSERT OR IGNORE INTO vocab_tipo (termo, tipo) VALUES
    ('quartos adulto',   'quartos adulto'),
    ('envios',           'envios'),
    ('envios especiais', 'envios'),
    ('eventos',          'eventos'),
    ('eventos - ok',     'eventos'),
    ('casa mooui',       'casa mooui');

-- Pastas tematicas da raiz podem ser adicionadas ao vocabulario conforme o acervo.
-- Ficam para v1.1: parser v1 so estrutura pastas de ano (^20\d{2}$).
-- Indexador v1 ainda VARRE essas pastas (embedding + paleta + FTS pelo path_raw),
-- mas as imagens ficam com status=nao_classificado ate a fase v1.1 modelar as regras.
-- Vocab abaixo documentado como referencia; injetar quando abrir v1.1:
--   INSERT OR IGNORE INTO vocab_tipo (termo, tipo) VALUES
--     ('insta', 'tematica'), ('instagram', 'tematica'), ('mockups', 'tematica'),
--     ('bastidores', 'tematica'), ('natal', 'tematica'), ('press', 'tematica'),
--     ('lookbook', 'tematica');

-- ============================================================================
-- sinonimos: expandem a busca textual para os termos presentes no acervo.
-- Cada grupo reune formas equivalentes; ao digitar qualquer uma, a busca
-- tambem procura as demais (ex.: "luminaria" encontra "abajur").
-- Termos ja normalizados (unidecode + lowercase). Curavel por instalacao.
-- ============================================================================
INSERT OR IGNORE INTO sinonimos (grupo, termo) VALUES
    ('organizador', 'organizador'),
    ('organizador', 'organizadora'),
    ('organizador', 'caixa organizadora'),
    ('organizador', 'caixas organizadoras'),
    ('organizador', 'cesto organizador'),
    ('organizador', 'cesto'),
    ('organizador', 'cesta'),
    ('organizador', 'porta treco'),
    ('organizador', 'canastra'),

    ('abajur', 'abajur'),
    ('abajur', 'luminaria'),
    ('abajur', 'lampada'),
    ('abajur', 'lampada de mesa'),

    ('edredom', 'edredom'),
    ('edredom', 'edredon'),
    ('edredom', 'duvet'),
    ('edredom', 'capa de edredom'),

    ('colcha', 'colcha'),
    ('colcha', 'cobreleito'),
    ('colcha', 'cobre leito'),
    ('colcha', 'cobre cama'),

    ('fronha', 'fronha'),
    ('fronha', 'capa de travesseiro'),
    ('fronha', 'porta travesseiro'),

    ('lencol', 'lencol'),
    ('lencol', 'roupa de cama'),

    ('jogo de cama', 'jogo de cama'),
    ('jogo de cama', 'jogos de cama'),
    ('jogo de cama', 'kit cama'),
    ('jogo de cama', 'conjunto de cama'),
    ('jogo de cama', 'roupa de cama'),

    ('almofada', 'almofada'),
    ('almofada', 'almofadao'),
    ('almofada', 'coxim'),

    ('tapete', 'tapete'),
    ('tapete', 'playmat'),
    ('tapete', 'tapete de atividades'),
    ('tapete', 'tapetinho'),
    ('tapete', 'tapete playmat'),

    ('trocador', 'trocador'),
    ('trocador', 'tapete de trocador'),

    ('tenda', 'tenda'),
    ('tenda', 'cabana'),
    ('tenda', 'tipi'),
    ('tenda', 'barraca'),

    ('cortina', 'cortina'),
    ('cortina', 'cortinado'),

    ('manta', 'manta'),
    ('manta', 'xale'),

    ('mochila', 'mochila'),
    ('mochila', 'bolsa'),
    ('mochila', 'sacola'),

    ('lancheira', 'lancheira'),
    ('lancheira', 'bolsa termica'),

    ('futon', 'futon'),
    ('futon', 'colchonete'),

    ('espreguicadeira', 'espreguicadeira'),
    ('espreguicadeira', 'cadeira de descanso'),

    ('pufe', 'pufe'),
    ('pufe', 'puff'),
    ('pufe', 'apoio para pes'),
    ('pufe', 'descanso de pes'),

    ('poltrona', 'poltrona'),
    ('poltrona', 'cadeira de amamentacao'),

    ('adesivo', 'adesivo'),
    ('adesivo', 'adesivo de parede'),
    ('adesivo', 'sticker'),

    ('papel de parede', 'papel de parede'),
    ('papel de parede', 'wallpaper'),
    ('papel de parede', 'revestimento de parede'),

    ('poster', 'poster'),
    ('poster', 'quadro'),
    ('poster', 'gravura'),
    ('poster', 'lamina'),

    ('regua de altura', 'regua de altura'),
    ('regua de altura', 'regua de crescimento'),
    ('regua de altura', 'medidor de altura'),

    ('necessaire', 'necessaire'),
    ('necessaire', 'estojo'),

    ('babador', 'babador'),
    ('babador', 'babeiro'),

    ('macacao', 'macacao'),
    ('macacao', 'jardineira'),
    ('macacao', 'macaquinho'),

    ('saco de roupa', 'saquinho roupa suja'),
    ('saco de roupa', 'saco de roupa suja'),
    ('saco de roupa', 'cesto de roupa'),

    ('toalha', 'toalha'),
    ('toalha', 'roupao'),

    ('minhocao', 'minhocao'),
    ('minhocao', 'rolo de berco'),
    ('minhocao', 'protetor de berco'),
    ('minhocao', 'rolinho de berco'),

    ('flamula', 'flamula'),
    ('flamula', 'bandeirinha'),
    ('flamula', 'galhardete'),

    ('adorno de parede', 'adorno de parede'),
    ('adorno de parede', 'enfeite de parede'),
    ('adorno de parede', 'decoracao de parede');

-- ============================================================================
-- config: parametros do indexador, embedder, API
-- ============================================================================
INSERT OR IGNORE INTO config (chave, valor, tipo, descricao) VALUES
    ('share_path',
     '/mnt/photo-library/photos',
     'string',
     'Ponto de montagem CIFS do acervo (modo ro). Ajustar por ambiente.'),

    ('share_readonly',
     'true',
     'bool',
     'Guarda: indexador aborta se o mount nao estiver ro (regra 1 CLAUDE.md).'),

    ('pastas_escopo',
     '["*"]',
     'json',
     'Lista de pastas da raiz a indexar. "*" representa todas.'),

    ('parser_escopo',
     '["ano"]',
     'json',
     'Escopo estrutural inicial: pastas de ano (20xx). Tematicas desconhecidas ficam como nao_classificado.'),

    ('extensoes_aceitas',
     '[".jpg", ".jpeg", ".png", ".webp"]',
     'json',
     'Extensoes tratadas como imagem. O resto vai para scan_runs.ignorados_nao_imagem.'),

    ('modelo_embedding',
     'sentence-transformers/clip-ViT-B-32-multilingual-v1',
     'string',
     'Modelo de texto multilingual PT-BR alinhado ao CLIP de imagem. Dim 512.'),

    ('modelo_embedding_imagem',
     'clip-ViT-B-32',
     'string',
     'Encoder visual original CLIP, alinhado ao modelo de texto multilingual.'),

    ('embedding_dim',
     '512',
     'int',
     'Dimensao do vetor. Deve casar com vec_imagens(embedding float[N]).'),

    ('batch_size',
     '32',
     'int',
     'Batch do embedder na CPU. Aumentar so' || ' se houver GPU.'),

    ('io_workers',
     '4',
     'int',
     'Leitores paralelos para thumbnails/proxies; reduz latencia SMB sem escrever no share.'),

    ('thumb_size',
     '512',
     'int',
     'Lado maior da thumbnail gerada quando nao ha' || ' REDUZIDA (px).'),

    ('thumb_quality',
     '80',
     'int',
     'Qualidade JPEG da thumbnail gerada (Pillow).'),

    ('thumbs_dir',
     'data/thumbnails',
     'string',
     'Diretorio de thumbs geradas, FORA do share (regra 1). Ajustar por ambiente.'),

    ('reduzidas_pasta_nome',
     'reduzidas',
     'string',
     'Nome (normalizado) da pasta de proxies. Match case-insensitive.'),

    ('segmentos_ignorados',
     '["0 - arquivos zip"]',
     'json',
     'Pastas administrativas/exportacao excluidas para evitar duplicatas no catalogo.'),

    ('paleta_k',
     '5',
     'int',
     'Numero de cores dominantes por imagem (k-means).'),

    ('paleta_deltae_threshold',
     '15.0',
     'float',
     'Delta E maximo para agrupar cores no filtro por swatch.'),

    ('cores_comerciais',
     '[{"nome":"Branco","hex":"#F5F2E8"},{"nome":"Bege","hex":"#D8C3A5"},{"nome":"Amarelo","hex":"#F2C94C"},{"nome":"Laranja","hex":"#F2994A"},{"nome":"Vermelho","hex":"#D94841"},{"nome":"Rosa","hex":"#E58AAE"},{"nome":"Roxo","hex":"#8E5AA7"},{"nome":"Azul","hex":"#4D83C4"},{"nome":"Verde","hex":"#5B8C5A"},{"nome":"Marrom","hex":"#7A5230"},{"nome":"Cinza","hex":"#9A9A9A"},{"nome":"Preto","hex":"#222222"}]',
     'json',
     'Vocabulario simples e estavel para filtros do site e atributo color do Google.'),

    ('cores_comerciais_max',
     '3',
     'int',
     'Maximo de cores por imagem/produto, compativel com Google Merchant Center.'),

    ('cores_comerciais_min_proporcao',
     '0.06',
     'float',
     'Ignora cores residuais abaixo desta proporcao antes da simplificacao.'),

    ('cores_marketing',
     '[{"nome":"Branco","hex":"#F7F5EF"},{"nome":"Creme","hex":"#FFF2D8"},{"nome":"Bege","hex":"#D8C3A5"},{"nome":"Areia","hex":"#C9A878"},{"nome":"Amarelo","hex":"#F2C94C"},{"nome":"Mostarda","hex":"#C89B2C"},{"nome":"Laranja","hex":"#F2994A"},{"nome":"Terracota","hex":"#B96545"},{"nome":"Vermelho","hex":"#D94841"},{"nome":"Vinho","hex":"#7B2D3E"},{"nome":"Rosa claro","hex":"#F3B7CB"},{"nome":"Rosa","hex":"#E58AAE"},{"nome":"Pink","hex":"#D94F91"},{"nome":"Lilas","hex":"#B89ACD"},{"nome":"Roxo","hex":"#7E57A0"},{"nome":"Azul claro","hex":"#9DCBE5"},{"nome":"Azul","hex":"#4D83C4"},{"nome":"Azul marinho","hex":"#263B66"},{"nome":"Turquesa","hex":"#43A7A5"},{"nome":"Verde menta","hex":"#A8D5BA"},{"nome":"Verde","hex":"#5B8C5A"},{"nome":"Verde oliva","hex":"#7C8447"},{"nome":"Marrom","hex":"#7A5230"},{"nome":"Cinza","hex":"#9A9A9A"},{"nome":"Preto","hex":"#222222"}]',
     'json',
     'Vocabulario de tons refinados para busca visual do time de marketing.'),

    ('cores_marketing_max',
     '4',
     'int',
     'Maximo de tons de marketing derivados por imagem.'),

    ('cores_marketing_min_proporcao',
     '0.04',
     'float',
     'Ignora tons residuais na paleta refinada.'),

    ('busca_imagem_max_bytes',
     '15728640',
     'int',
     'Tamanho maximo da imagem temporaria usada em busca por similaridade.');

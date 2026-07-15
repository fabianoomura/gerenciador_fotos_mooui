"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const POR_PAGINA = 60;

type Cor = { nome?: string; hex: string; proporcao?: number; peso?: number };
type Foto = {
  id: number;
  path: string;
  ano?: number;
  tipo?: string;
  colecao?: string;
  categoria?: string;
  pessoa?: string;
  pessoa_tipo?: string;
  variante?: string;
  ambiente_tema?: string;
  paleta?: Cor[];
  cores_comerciais?: Cor[];
  cores_marketing?: Cor[];
};
type Faceta = { valor: string | number; total: number };
type Facetas = Record<string, Faceta[]>;

export default function Home() {
  const [fotos, setFotos] = useState<Foto[]>([]);
  const [facetas, setFacetas] = useState<Facetas>({});
  const [swatches, setSwatches] = useState<Cor[]>([]);
  const [q, setQ] = useState("");
  const [anos, setAnos] = useState<string[]>(["2026"]);
  const [tipos, setTipos] = useState<string[]>([]);
  const [papeis, setPapeis] = useState<string[]>([]);
  const [pessoas, setPessoas] = useState<string[]>([]);
  const [paletaModo, setPaletaModo] = useState<"comercial" | "marketing">("comercial");
  const [ordenacao, setOrdenacao] = useState<"recentes" | "antigas" | "relevancia">("recentes");
  const [cor, setCor] = useState("");
  const [buscaImagemAtiva, setBuscaImagemAtiva] = useState(false);
  const [imagemReferencia, setImagemReferencia] = useState("");
  const [imagemArquivo, setImagemArquivo] = useState<Blob | null>(null);
  const [erroImagem, setErroImagem] = useState("");
  const [pagina, setPagina] = useState(1);
  const [total, setTotal] = useState<number | null>(null);
  const [temProxima, setTemProxima] = useState(false);
  const [selecionada, setSelecionada] = useState<Foto | null>(null);
  const [statusCopia, setStatusCopia] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function copiarCaminho() {
    if (!selecionada) return;
    setStatusCopia("");
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(selecionada.path);
      } else {
        const campo = document.createElement("textarea");
        campo.value = selecionada.path;
        campo.style.position = "fixed";
        campo.style.opacity = "0";
        document.body.appendChild(campo);
        campo.focus();
        campo.select();
        const copiou = document.execCommand("copy");
        campo.remove();
        if (!copiou) throw new Error("Cópia bloqueada pelo navegador");
      }
      setStatusCopia("Caminho copiado!");
    } catch {
      setStatusCopia("Não foi possível copiar. Selecione o caminho acima manualmente.");
    }
  }

  async function carregar(parametros: URLSearchParams, paginaAtual = 1) {
    setCarregando(true);
    try {
      parametros.set("limit", String(POR_PAGINA));
      parametros.set("offset", String((paginaAtual - 1) * POR_PAGINA));
      const resposta = await fetch(`${API}/busca?${parametros}`);
      const dados = await resposta.json();
      setFotos(dados.items ?? []);
      setPagina(paginaAtual);
      setTotal(dados.total ?? null);
      setTemProxima(Boolean(dados.has_more));
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    fetch(`${API}/facetas`).then((r) => r.json()).then(setFacetas);
  }, []);

  useEffect(() => {
    fetch(`${API}/paleta/swatches?modo=${paletaModo}&limit=40`)
      .then((r) => r.json())
      .then((dados) => setSwatches(dados.items ?? []));
  }, [paletaModo]);

  function parametrosAtuais() {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    anos.forEach((valor) => params.append("ano", valor));
    tipos.forEach((valor) => params.append("tipo", valor));
    papeis.forEach((valor) => params.append("pessoa_tipo", valor));
    pessoas.forEach((valor) => params.append("pessoa", valor));
    if (cor) params.set(paletaModo === "comercial" ? "cor" : "tom", cor);
    return params;
  }

  useEffect(() => {
    if (!buscaImagemAtiva) carregar(parametrosAtuais(), 1);
  }, [anos, tipos, papeis, pessoas, cor, paletaModo, buscaImagemAtiva]);

  useEffect(() => {
    function colarImagem(evento: ClipboardEvent) {
      const arquivo = Array.from(evento.clipboardData?.items ?? [])
        .find((item) => item.type.startsWith("image/"))
        ?.getAsFile();
      if (arquivo) buscarPorImagem(arquivo);
    }
    window.addEventListener("paste", colarImagem);
    return () => window.removeEventListener("paste", colarImagem);
  }, []);

  function buscar(event?: FormEvent) {
    event?.preventDefault();
    if (buscaImagemAtiva) {
      setBuscaImagemAtiva(false);
      return;
    }
    carregar(parametrosAtuais(), 1);
  }

  function alternar(valor: string, atuais: string[], atualizar: (valores: string[]) => void) {
    setBuscaImagemAtiva(false);
    atualizar(
      atuais.includes(valor)
        ? atuais.filter((item) => item !== valor)
        : [...atuais, valor],
    );
  }

  function limparFiltros() {
    setQ("");
    setAnos([]);
    setTipos([]);
    setPapeis([]);
    setPessoas([]);
    setCor("");
    setBuscaImagemAtiva(false);
  }

  async function buscarPorImagem(arquivo: Blob, paginaAtual = 1) {
    if (!arquivo.type.startsWith("image/")) {
      setErroImagem("Escolha um arquivo de imagem.");
      return;
    }
    setErroImagem("");
    setCarregando(true);
    setBuscaImagemAtiva(true);
    if (paginaAtual === 1) {
      setOrdenacao("relevancia");
      setImagemArquivo(arquivo);
      if (imagemReferencia) URL.revokeObjectURL(imagemReferencia);
      setImagemReferencia(URL.createObjectURL(arquivo));
    }
    try {
      const offset = (paginaAtual - 1) * POR_PAGINA;
      const resposta = await fetch(
        `${API}/busca/por-imagem?limit=${POR_PAGINA}&offset=${offset}`,
        {
        method: "POST",
        headers: { "Content-Type": arquivo.type },
        body: arquivo,
        },
      );
      if (!resposta.ok) {
        const detalhe = await resposta.json().catch(() => ({}));
        throw new Error(detalhe.detail ?? "Não foi possível analisar a imagem.");
      }
      const dados = await resposta.json();
      setFotos(dados.items ?? []);
      setPagina(paginaAtual);
      setTotal(null);
      setTemProxima(Boolean(dados.has_more));
    } catch (erro) {
      setErroImagem(erro instanceof Error ? erro.message : "Erro ao analisar a imagem.");
      setBuscaImagemAtiva(false);
    } finally {
      setCarregando(false);
    }
  }

  function trocarModoPaleta(modo: "comercial" | "marketing") {
    setBuscaImagemAtiva(false);
    setPaletaModo(modo);
    setCor("");
  }

  function irParaPagina(novaPagina: number) {
    if (novaPagina < 1 || carregando) return;
    if (buscaImagemAtiva && imagemArquivo) {
      buscarPorImagem(imagemArquivo, novaPagina);
    } else {
      carregar(parametrosAtuais(), novaPagina);
    }
    const galeria = document.querySelector(".gallery");
    const topo = galeria ? window.scrollY + galeria.getBoundingClientRect().top - 90 : 0;
    window.scrollTo({ top: topo, behavior: "smooth" });
  }

  const anosOrdenados = useMemo(
    () => [...(facetas.ano ?? [])].sort((a, b) => Number(b.valor) - Number(a.valor)),
    [facetas],
  );

  const fotosOrdenadas = useMemo(() => {
    if (ordenacao === "relevancia") return fotos;
    return [...fotos].sort((a, b) => {
      if (a.ano == null && b.ano == null) return b.id - a.id;
      if (a.ano == null) return 1;
      if (b.ano == null) return -1;
      const diferenca = ordenacao === "recentes" ? b.ano - a.ano : a.ano - b.ano;
      return diferenca || (ordenacao === "recentes" ? b.id - a.id : a.id - b.id);
    });
  }, [fotos, ordenacao]);

  const totalPaginas = total == null ? null : Math.max(1, Math.ceil(total / POR_PAGINA));
  const paginasVisiveis = useMemo(() => {
    const ultima = totalPaginas ?? (temProxima ? pagina + 1 : pagina);
    const inicio = Math.max(1, Math.min(pagina - 1, ultima - 2));
    return Array.from({ length: Math.min(3, ultima) }, (_, indice) => inicio + indice)
      .filter((numero) => numero <= ultima);
  }, [pagina, totalPaginas, temProxima]);
  const resumo = useMemo(
    () => total == null
      ? `${fotos.length} imagens na página ${pagina}`
      : `${total.toLocaleString("pt-BR")} imagens · página ${pagina} de ${totalPaginas}`,
    [fotos.length, pagina, total, totalPaginas],
  );

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#">
          <img className="brandLogo" src="/catalog-icon.svg" alt="" />
          <span>Foto Catálogo <small>pesquisa visual</small></span>
        </a>
        <form className="search" onSubmit={buscar}>
          <span aria-hidden>⌕</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Busque: quarto colorido, fada, acampamento..."
          />
          <button>Buscar</button>
        </form>
        <div className="status"><i /> acervo completo</div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">ACERVO CRIATIVO</p>
          <h1>A foto certa,<br /><em>sem perder tempo.</em></h1>
          <p>Explore o acervo por significado, cor, coleção ou pessoa.</p>
        </div>
        <div className="heroShapes" aria-hidden><b /><b /><b /></div>
      </section>

      <div className="workspace">
        <aside className="filters">
          <div className="filterTitle"><strong>Filtros</strong><button onClick={limparFiltros}>limpar</button></div>
          <label
            className="imageFinder"
            onDragOver={(evento) => evento.preventDefault()}
            onDrop={(evento) => {
              evento.preventDefault();
              const arquivo = evento.dataTransfer.files[0];
              if (arquivo) buscarPorImagem(arquivo);
            }}
          >
            <input
              type="file"
              accept="image/*"
              onChange={(evento) => {
                const arquivo = evento.target.files?.[0];
                if (arquivo) buscarPorImagem(arquivo);
                evento.target.value = "";
              }}
            />
            <span aria-hidden>◎</span>
            <strong>Buscar por imagem</strong>
            <small>Cole, arraste ou selecione uma foto</small>
          </label>
          {erroImagem && <p className="imageError">{erroImagem}</p>}
          <label>Ano</label>
          <div className="yearButtons">
            {anosOrdenados.map((item) => {
              const valor = String(item.valor);
              return <button
                type="button"
                className={anos.includes(valor) ? "active" : ""}
                key={valor}
                onClick={() => alternar(valor, anos, setAnos)}
              ><strong>{valor}</strong><small>{item.total}</small></button>;
            })}
          </div>
          <label>Tipo</label>
          <div className="chips">
            {(facetas.tipo ?? []).map((item) => {
              const valor = String(item.valor);
              return <button
                type="button"
                className={tipos.includes(valor) ? "active" : ""}
                key={valor}
                onClick={() => alternar(valor, tipos, setTipos)}
              >{valor} <small>{item.total}</small></button>;
            })}
          </div>
          <label>Perfil</label>
          <div className="chips profileChips">
            {(facetas.pessoa_tipo ?? []).map((item) => {
              const valor = String(item.valor);
              return <button
                type="button"
                className={papeis.includes(valor) ? "active" : ""}
                key={valor}
                onClick={() => alternar(valor, papeis, setPapeis)}
              >{valor} <small>{item.total}</small></button>;
            })}
          </div>
          <details className="filterDetails">
            <summary>Pessoas <span>{pessoas.length ? `${pessoas.length} selecionadas` : "escolher"}</span></summary>
            <div className="checkList">
              {(facetas.pessoa ?? []).map((item) => {
                const valor = String(item.valor);
                return <label key={valor}>
                  <input
                    type="checkbox"
                    checked={pessoas.includes(valor)}
                    onChange={() => alternar(valor, pessoas, setPessoas)}
                  />
                  <span>{valor}</span><small>{item.total}</small>
                </label>;
              })}
            </div>
          </details>
          <label>Paleta</label>
          <div className="paletteModes">
            <button
              type="button"
              className={paletaModo === "comercial" ? "active" : ""}
              onClick={() => trocarModoPaleta("comercial")}
            >Site / Google</button>
            <button
              type="button"
              className={paletaModo === "marketing" ? "active" : ""}
              onClick={() => trocarModoPaleta("marketing")}
            >Tons visuais</button>
          </div>
          <div className="swatches">
            {swatches.map((item) => <button
              className={cor === item.nome ? "selected" : ""}
              key={item.nome ?? item.hex}
              title={item.nome ?? item.hex}
              style={{ background: item.hex }}
              onClick={() => {
                setBuscaImagemAtiva(false);
                const proxima = item.nome ?? "";
                setCor(cor === proxima ? "" : proxima);
              }}
            />)}
          </div>
          <div className="tip"><span>✦</span><p><strong>Dica</strong> Combine texto e filtros para resultados mais precisos.</p></div>
        </aside>

        <section className="gallery">
          {buscaImagemAtiva && imagemReferencia && <div className="imageReference">
            <img src={imagemReferencia} alt="Imagem usada como referência" />
            <div><span>BUSCA VISUAL</span><strong>Fotos semelhantes à sua referência</strong></div>
            <button onClick={() => setBuscaImagemAtiva(false)}>remover referência</button>
          </div>}
          <div className="galleryHead">
            <div><span>RESULTADOS</span><strong>{resumo}</strong></div>
            <label className="sortControl">
              <span>Ordenar</span>
              <select
                value={ordenacao}
                onChange={(evento) => setOrdenacao(evento.target.value as typeof ordenacao)}
              >
                <option value="recentes">Mais novas primeiro</option>
                <option value="antigas">Mais antigas primeiro</option>
                <option value="relevancia">Mais relevantes</option>
              </select>
            </label>
          </div>
          {carregando && <div className="loading">Procurando no acervo…</div>}
          {!carregando && <div className="masonry">
            {fotosOrdenadas.map((foto) => (
              <article className="card" key={foto.id} onClick={() => { setSelecionada(foto); setStatusCopia(""); }}>
                <img src={`${API}/imagens/${foto.id}/thumb`} alt={foto.ambiente_tema ?? foto.categoria ?? "Foto do acervo"} loading="lazy" />
                <div className="cardOverlay">
                  <div className="tags"><span>{foto.ano}</span>{foto.tipo && <span>{foto.tipo}</span>}</div>
                  <button aria-label="Abrir detalhes">↗</button>
                </div>
                <div className="miniPalette">{(
                  paletaModo === "marketing"
                    ? foto.cores_marketing
                    : foto.cores_comerciais
                )?.slice(0, 4).map((c) => <i key={c.nome ?? c.hex} title={c.nome} style={{ background: c.hex }} />)}</div>
              </article>
            ))}
          </div>}
          {!carregando && (pagina > 1 || temProxima) && <nav className="pagination" aria-label="Páginas de resultados">
            <button disabled={pagina === 1} onClick={() => irParaPagina(pagina - 1)}>Anterior</button>
            <div>
              {paginasVisiveis.map((numero) => <button
                className={numero === pagina ? "active" : ""}
                key={numero}
                onClick={() => irParaPagina(numero)}
              >{numero}</button>)}
            </div>
            <button disabled={!temProxima} onClick={() => irParaPagina(pagina + 1)}>Próxima</button>
          </nav>}
        </section>
      </div>

      {selecionada && <div className="modalBackdrop" onClick={() => setSelecionada(null)}>
        <section className="modal" onClick={(e) => e.stopPropagation()}>
          <button className="close" onClick={() => setSelecionada(null)}>×</button>
          <img src={`${API}/imagens/${selecionada.id}/thumb`} alt="" />
          <div className="details">
            <p className="eyebrow">IMAGEM #{selecionada.id}</p>
            <h2>{selecionada.ambiente_tema ?? selecionada.categoria ?? selecionada.tipo ?? "Foto do acervo"}</h2>
            <dl>
              <dt>Ano</dt><dd>{selecionada.ano ?? "—"}</dd>
              <dt>Coleção</dt><dd>{selecionada.colecao ?? "—"}</dd>
              <dt>Pessoa</dt><dd>{selecionada.pessoa ?? "—"}</dd>
              <dt>Variante</dt><dd>{selecionada.variante ?? "original"}</dd>
            </dl>
            <div className="path">{selecionada.path}</div>
            <div className="modalActions">
              <button className="primary" onClick={copiarCaminho}>Copiar caminho</button>
              <a className="primary secondary" href={`${API}/imagens/${selecionada.id}/download`}>
                Baixar original
              </a>
            </div>
            {statusCopia && <p className="copyStatus" role="status">{statusCopia}</p>}
          </div>
        </section>
      </div>}
    </main>
  );
}

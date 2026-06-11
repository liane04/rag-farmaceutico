// Vistas exclusivas do admin: documentos (com upload) e auditoria.
// Cada vista renderiza-se num container e tem o seu proprio loader.

import { apiFetch, apiGet, apiPostForm, formatarDetalheErro, humanizarErro, rotuloTipo } from './api.js';
import { mountCustomSelect, getCustomSelectValue } from './dropdown.js';

const CHEVRON_SVG = `<svg class="custom-select-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;

// ============ Vista: Documentos + Upload ============
export function renderDocumentos(container) {
    container.innerHTML = `
        <div class="container">
            <div class="upload-card">
                <div class="upload-title">Adicionar Documento</div>
                <div class="upload-form">
                    <div class="upload-field">
                        <label>Ficheiro PDF</label>
                        <div class="upload-file-wrapper">
                            <label for="uploadFile" class="upload-file-button">Escolher ficheiro</label>
                            <span class="upload-file-name" id="uploadFileName">Nenhum ficheiro selecionado</span>
                            <input type="file" id="uploadFile" accept=".pdf" class="upload-file-hidden">
                        </div>
                    </div>
                    <div class="upload-field">
                        <label>Tipo de documento</label>
                        <div class="custom-select" id="uploadTipo" data-value="bula">
                            <button type="button" class="custom-select-button" aria-haspopup="listbox" aria-expanded="false">
                                <span class="custom-select-label">Bula / RCM</span>
                                ${CHEVRON_SVG}
                            </button>
                            <ul class="custom-select-menu" role="listbox" hidden>
                                <li class="custom-select-option" data-value="bula" role="option">Bula / RCM</li>
                                <li class="custom-select-option" data-value="monografia" role="option">Monografia</li>
                                <li class="custom-select-option" data-value="guideline" role="option">Guideline</li>
                                <li class="custom-select-option" data-value="norma" role="option">Norma</li>
                            </ul>
                        </div>
                    </div>
                    <button class="upload-btn" id="uploadBtn">Enviar e Indexar</button>
                </div>
                <div class="upload-status" id="uploadStatus"></div>
            </div>

            <div class="stats-bar">
                <div class="stat-card">
                    <div class="stat-card-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>
                    </div>
                    <div class="stat-card-body">
                        <div class="stat-value" id="statDocs2">-</div>
                        <div class="stat-label">Total Documentos</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                    </div>
                    <div class="stat-card-body">
                        <div class="stat-value" id="statChunks2">-</div>
                        <div class="stat-label">Total Chunks</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                    </div>
                    <div class="stat-card-body">
                        <div class="stat-value" id="statPaginas">-</div>
                        <div class="stat-label">Total Paginas</div>
                    </div>
                </div>
            </div>
            <div class="docs-toolbar">
                <input type="text" class="docs-search" id="docsSearch"
                       placeholder="Pesquisar por nome..." autocomplete="off">
                <div class="custom-select" id="docsTipoFilter" data-value="">
                    <button type="button" class="custom-select-button" aria-haspopup="listbox" aria-expanded="false">
                        <span class="custom-select-label">Todos os tipos</span>
                        ${CHEVRON_SVG}
                    </button>
                    <ul class="custom-select-menu" role="listbox" hidden>
                        <li class="custom-select-option" data-value="" role="option">Todos os tipos</li>
                        <li class="custom-select-option" data-value="bula" role="option">Bulas e RCM</li>
                        <li class="custom-select-option" data-value="monografia" role="option">Monografias</li>
                        <li class="custom-select-option" data-value="guideline" role="option">Guidelines</li>
                        <li class="custom-select-option" data-value="norma" role="option">Normas</li>
                    </ul>
                </div>
                <div class="custom-select" id="docsSort" data-value="nome">
                    <button type="button" class="custom-select-button" aria-haspopup="listbox" aria-expanded="false">
                        <span class="custom-select-label">Nome (A-Z)</span>
                        ${CHEVRON_SVG}
                    </button>
                    <ul class="custom-select-menu" role="listbox" hidden>
                        <li class="custom-select-option" data-value="nome" role="option">Nome (A-Z)</li>
                        <li class="custom-select-option" data-value="tipo" role="option">Tipo</li>
                        <li class="custom-select-option" data-value="chunks" role="option">Mais chunks</li>
                    </ul>
                </div>
                <span class="docs-count" id="docsCount"></span>
            </div>
            <div class="docs-grid" id="docsGrid">
                <div class="audit-empty">A carregar documentos...</div>
            </div>
        </div>
    `;
    document.getElementById('uploadBtn').addEventListener('click', uploadDocument);
    mountCustomSelect(document.getElementById('uploadTipo'));
    // Mostrar nome do ficheiro escolhido ao lado do botao "Escolher ficheiro".
    document.getElementById('uploadFile').addEventListener('change', (e) => {
        const nome = e.target.files && e.target.files[0] ? e.target.files[0].name : 'Nenhum ficheiro selecionado';
        document.getElementById('uploadFileName').textContent = nome;
    });
    // Toolbar de filtro/ordenacao da grelha — re-renderiza sobre a cache local.
    mountCustomSelect(document.getElementById('docsTipoFilter'));
    mountCustomSelect(document.getElementById('docsSort'));
    document.getElementById('docsSearch').addEventListener('input', _renderDocsGrid);
    document.getElementById('docsTipoFilter').addEventListener('change', _renderDocsGrid);
    document.getElementById('docsSort').addEventListener('change', _renderDocsGrid);
    loadDocumentos();
}

async function uploadDocument() {
    const fileInput = document.getElementById('uploadFile');
    const tipo = getCustomSelectValue(document.getElementById('uploadTipo'));
    const btn = document.getElementById('uploadBtn');
    const status = document.getElementById('uploadStatus');

    if (!fileInput.files || fileInput.files.length === 0) {
        status.className = 'upload-status active error';
        status.innerHTML = '&#9888; Selecione um ficheiro PDF.';
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        status.className = 'upload-status active error';
        status.innerHTML = '&#9888; Apenas ficheiros PDF sao aceites.';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'A processar...';
    status.className = 'upload-status active loading';
    status.innerHTML = '<div class="spinner-small"></div> A enviar e indexar o documento...';

    try {
        const formData = new FormData();
        formData.append('ficheiro', file);
        formData.append('tipo_documento', tipo);

        const data = await apiPostForm('/upload', formData);

        const perdidos = data.chunks_gerados - data.pontos_indexados;
        const aviso = perdidos > 0 ? ` &#9888; ${perdidos} chunk(s) não foram indexados.` : '';
        status.className = 'upload-status active success';
        status.innerHTML = `&#10003; Documento indexado: ${data.chunks_gerados} chunks gerados, ${data.pontos_indexados} indexados, ${data.total_na_collection} pontos totais.${aviso}`;

        fileInput.value = '';
        document.getElementById('uploadFileName').textContent = 'Nenhum ficheiro selecionado';
        loadDocumentos();
    } catch (err) {
        status.className = 'upload-status active error';
        status.innerHTML = `&#9888; ${escapeHtml(humanizarErro(err.message, 'indexacao'))}`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Enviar e Indexar';
    }
}

// Cache da lista de documentos — a toolbar filtra/ordena sobre isto sem
// voltar a pedir a API; o loadDocumentos atualiza-a (upload, delete, refresh).
let _docsCache = [];

async function loadDocumentos() {
    const grid = document.getElementById('docsGrid');
    try {
        const data = await apiGet('/documentos');

        document.getElementById('statDocs2').textContent = data.total_documentos;
        document.getElementById('statChunks2').textContent = data.total_chunks;

        let totalPaginas = 0;
        data.documentos.forEach(d => totalPaginas += d.paginas.length);
        document.getElementById('statPaginas').textContent = totalPaginas;

        _docsCache = data.documentos;
        _renderDocsGrid();
    } catch (err) {
        _markStatsAdminUnavailable();
        grid.innerHTML = `<div class="audit-empty">${escapeHtml(humanizarErro(err.message))}</div>`;
    }
}

function _renderDocsGrid() {
    const grid = document.getElementById('docsGrid');
    if (!grid) return;

    const termo = (document.getElementById('docsSearch')?.value || '').trim().toLowerCase();
    const tipo = getCustomSelectValue(document.getElementById('docsTipoFilter'));
    const ordem = getCustomSelectValue(document.getElementById('docsSort')) || 'nome';

    const docs = _docsCache.filter(d =>
        (!tipo || d.tipo_documento === tipo) &&
        (!termo || (d.ficheiro || '').toLowerCase().includes(termo))
    );

    const porNome = (a, b) => (a.ficheiro || '').localeCompare(b.ficheiro || '', 'pt', { sensitivity: 'base' });
    if (ordem === 'chunks') docs.sort((a, b) => (b.total_chunks - a.total_chunks) || porNome(a, b));
    else if (ordem === 'tipo') docs.sort((a, b) => (a.tipo_documento || '').localeCompare(b.tipo_documento || '') || porNome(a, b));
    else docs.sort(porNome);

    const count = document.getElementById('docsCount');
    if (count) {
        count.textContent = docs.length === _docsCache.length
            ? `${_docsCache.length} documento${_docsCache.length === 1 ? '' : 's'}`
            : `${docs.length} de ${_docsCache.length} documentos`;
    }

    if (_docsCache.length === 0) {
        grid.innerHTML = '<div class="audit-empty">Nenhum documento indexado.</div>';
        return;
    }
    if (docs.length === 0) {
        grid.innerHTML = '<div class="audit-empty">Nenhum documento corresponde ao filtro.</div>';
        return;
    }

    grid.innerHTML = '';
    docs.forEach(doc => {
            const typeClass = 'doc-type-' + (doc.tipo_documento || 'desconhecido');
            const card = document.createElement('div');
            card.className = 'doc-card';
            card.innerHTML = `
                <div class="doc-card-header">
                    <span class="doc-name">${escapeHtml(doc.ficheiro)}</span>
                    <span class="doc-type-badge ${typeClass}">${escapeHtml(rotuloTipo(doc.tipo_documento))}</span>
                </div>
                <div class="doc-card-body">
                    <div class="doc-stat-row">
                        <span class="doc-stat-label">Chunks indexados</span>
                        <span class="doc-stat-value">${doc.total_chunks}</span>
                    </div>
                    <div class="doc-stat-row">
                        <span class="doc-stat-label">Paginas</span>
                        <span class="doc-stat-value">${doc.paginas.length}</span>
                    </div>
                    <div class="doc-stat-row">
                        <span class="doc-stat-label">Intervalo de paginas</span>
                        <span class="doc-stat-value">${doc.paginas[0]} - ${doc.paginas[doc.paginas.length - 1]}</span>
                    </div>
                </div>
                <div class="doc-card-footer">
                    <button class="doc-delete-btn" title="Remover do índice e apagar o PDF">Apagar</button>
                </div>
            `;
            card.querySelector('.doc-delete-btn').addEventListener('click', () =>
                apagarDocumento(doc.tipo_documento, doc.ficheiro, card));
            grid.appendChild(card);
    });
}

// Modal de confirmacao em-app (substitui o window.confirm nativo).
// Devolve uma Promise<boolean>: true se o utilizador confirmar.
function confirmarModal({ titulo, mensagem, textoConfirmar = 'Confirmar' }) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modalTitulo">
                <div class="modal-title" id="modalTitulo">${titulo}</div>
                <div class="modal-text">${mensagem}</div>
                <div class="modal-actions">
                    <button type="button" class="modal-btn modal-btn-cancel">Cancelar</button>
                    <button type="button" class="modal-btn modal-btn-danger">${textoConfirmar}</button>
                </div>
            </div>
        `;
        const fechar = (valor) => {
            document.removeEventListener('keydown', onKey);
            overlay.remove();
            resolve(valor);
        };
        const onKey = (e) => { if (e.key === 'Escape') fechar(false); };
        overlay.addEventListener('click', (e) => { if (e.target === overlay) fechar(false); });
        overlay.querySelector('.modal-btn-cancel').addEventListener('click', () => fechar(false));
        overlay.querySelector('.modal-btn-danger').addEventListener('click', () => fechar(true));
        document.addEventListener('keydown', onKey);
        document.body.appendChild(overlay);
        overlay.querySelector('.modal-btn-cancel').focus();
    });
}

async function apagarDocumento(tipo, ficheiro, card) {
    const confirmado = await confirmarModal({
        titulo: `Apagar "${escapeHtml(ficheiro)}"?`,
        mensagem: 'Isto remove o documento do índice de pesquisa e apaga o PDF.<br>' +
                  'A ação é irreversível. O documento só volta com novo upload.',
        textoConfirmar: 'Apagar',
    });
    if (!confirmado) return;

    const btn = card.querySelector('.doc-delete-btn');
    btn.disabled = true;
    btn.textContent = 'A apagar...';
    try {
        const res = await apiFetch(`/documentos/${encodeURIComponent(tipo)}/${encodeURIComponent(ficheiro)}`, {
            method: 'DELETE',
        });
        if (!res.ok) {
            const erro = await res.json().catch(() => ({}));
            throw new Error(erro.detail || `Erro ${res.status}`);
        }
        const data = await res.json();
        // Recarrega a grelha e as stats — o cartao desaparece.
        await loadDocumentos();
        const status = document.getElementById('uploadStatus');
        if (status) {
            status.className = 'upload-status active success';
            status.textContent = `"${ficheiro}" apagado (${data.chunks_removidos} chunks removidos do índice).`;
        }
    } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Apagar';
        const status = document.getElementById('uploadStatus');
        if (status) {
            status.className = 'upload-status active error';
            status.textContent = `Não foi possível apagar "${ficheiro}": ${err.message}`;
        }
    }
}

// Espelha o markStatsUnavailable do chat.js, mas para os ids da vista admin.
function _markStatsAdminUnavailable() {
    for (const id of ['statDocs2', 'statChunks2', 'statPaginas']) {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = '—';
            el.classList.add('unavailable');
        }
    }
}

// ============ Vista: Auditoria (todas as consultas) ============
export function renderAuditoria(container) {
    container.innerHTML = `
        <div class="container">
            <div class="audit-controls">
                <span class="audit-title">Histórico de Consultas (todos os utilizadores)</span>
                <div style="display:flex; gap:0.5rem; align-items:center;">
                    <span class="audit-count" id="auditCount">0 registos</span>
                    <button class="search-btn" id="auditRefreshBtn" style="padding:0.5rem 1rem; font-size:0.8rem;">Atualizar</button>
                </div>
            </div>
            <div class="audit-table-wrapper">
                <table class="audit-table">
                    <thead>
                        <tr>
                            <th>Hora</th>
                            <th>Utilizador</th>
                            <th>Query</th>
                            <th>Fontes</th>
                            <th>Contexto</th>
                            <th>Duração</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="auditBody">
                        <tr>
                            <td colspan="7" class="audit-empty">A carregar...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;
    document.getElementById('auditRefreshBtn').addEventListener('click', loadAudit);
    loadAudit();
}

async function loadAudit() {
    const body = document.getElementById('auditBody');
    try {
        const data = await apiGet('/audit');

        document.getElementById('auditCount').textContent = `${data.total} registos`;

        if (data.total === 0) {
            body.innerHTML = '<tr><td colspan="7" class="audit-empty">Nenhuma consulta registada.</td></tr>';
            return;
        }

        body.innerHTML = '';
        data.registos.forEach((reg, i) => {
            const hora = formatarHora(reg.timestamp);
            const fontes = (reg.fontes || []).map(f =>
                `<span class="audit-source-mini">${escapeHtml(f.ficheiro || '?')}</span>`
            ).join('');
            const ctxClass = reg.contexto_suficiente ? 'audit-context-ok' : 'audit-context-warn';
            const ctxText = reg.contexto_suficiente ? 'OK' : 'Limitado';
            const duracao = reg.duracao_segundos ? reg.duracao_segundos.toFixed(1) + 's' : '-';
            const utilizador = reg.utilizador
                ? `<span class="audit-user">${escapeHtml(reg.utilizador)}</span> <span class="audit-role">${escapeHtml(reg.papel || '')}</span>`
                : '<span class="audit-user audit-user-anon">(anónimo)</span>';

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="audit-time">${hora}</td>
                <td>${utilizador}</td>
                <td class="audit-query" title="${escapeHtml(reg.query_original)}">${escapeHtml(reg.query_original)}</td>
                <td><div class="audit-sources">${fontes}</div></td>
                <td><span class="audit-context-badge ${ctxClass}">${ctxText}</span></td>
                <td><span class="audit-duration">${duracao}</span></td>
                <td><button class="audit-expand-btn" data-idx="${i}">Ver</button></td>
            `;
            body.appendChild(tr);

            const detailTr = document.createElement('tr');
            detailTr.id = `audit-detail-${i}`;
            detailTr.style.display = 'none';
            detailTr.innerHTML = `
                <td colspan="7" style="padding:0;">
                    <div style="padding:1rem 1.25rem; background:#f8fafc; border-top:1px solid var(--border);">
                        <div class="audit-detail-label">Query usada</div>
                        <p style="margin-bottom:0.75rem; font-size:0.85rem;">${escapeHtml(reg.query_usada || '-')}</p>
                        <div class="audit-detail-label">Resposta</div>
                        <div class="audit-detail-response">${escapeHtml(reg.resposta || '-')}</div>
                    </div>
                </td>
            `;
            body.appendChild(detailTr);
        });

        body.querySelectorAll('.audit-expand-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = btn.getAttribute('data-idx');
                const row = document.getElementById(`audit-detail-${idx}`);
                row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
            });
        });
    } catch (err) {
        body.innerHTML = `<tr><td colspan="7" class="audit-empty">Erro ao carregar auditoria: ${escapeHtml(err.message)}</td></tr>`;
    }
}

// ============ Vista: Definicoes (admin) ============
export function renderDefinicoes(container) {
    container.innerHTML = `
        <div class="container">
            <div class="settings-card">
                <div class="settings-title">Modo de geração (LLM)</div>
                <div class="settings-desc">
                    Escolhe qual modelo o sistema usa para reranking, avaliação
                    de contexto, geração de resposta e verificação de fidelidade.
                </div>

                <div class="settings-row" id="llmModeRow">
                    <div class="settings-current">
                        <div class="settings-current-label">Modo activo</div>
                        <div class="settings-current-value" id="llmModeAtual">A carregar...</div>
                        <div class="settings-current-model" id="llmModeModelo">-</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" id="llmModeToggle" disabled>
                        <span class="toggle-slider"></span>
                        <span class="toggle-label-on">Local</span>
                        <span class="toggle-label-off">Online</span>
                    </label>
                </div>

                <div class="settings-info">
                    <div class="settings-info-block">
                        <div class="settings-info-title">Online (Claude)</div>
                        <div class="settings-info-text">
                            Qualidade máxima. Dados são enviados para a Anthropic.
                            Recomendado para casos sem restrições de soberania de dados.
                        </div>
                    </div>
                    <div class="settings-info-block">
                        <div class="settings-info-title">Local (Ollama)</div>
                        <div class="settings-info-text">
                            Dados ficam na máquina servidor. Qualidade depende do modelo
                            instalado. Recomendado para contextos com requisitos RGPD/clínicos.
                        </div>
                    </div>
                </div>

                <div class="settings-status" id="llmModeStatus"></div>
            </div>
        </div>
    `;
    loadLlmMode();
    document.getElementById('llmModeToggle').addEventListener('change', toggleLlmMode);
}

async function loadLlmMode() {
    const status = document.getElementById('llmModeStatus');
    try {
        const data = await apiGet('/admin/llm-mode');
        _renderLlmMode(data);
    } catch (err) {
        status.className = 'settings-status active error';
        status.textContent = formatarDetalheErro(err.message);
    }
}

async function toggleLlmMode(e) {
    const toggle = document.getElementById('llmModeToggle');
    const status = document.getElementById('llmModeStatus');
    const novoModo = e.target.checked ? 'local' : 'online';

    toggle.disabled = true;
    status.className = 'settings-status active loading';
    status.innerHTML = '<div class="spinner-small"></div> A alterar...';

    try {
        const res = await apiFetch('/admin/llm-mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modo: novoModo }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || 'Erro');
        await loadLlmMode();
        status.className = 'settings-status active success';
        status.textContent = `Modo alterado para "${novoModo}". Afeta todas as consultas seguintes.`;
    } catch (err) {
        toggle.checked = !e.target.checked;
        status.className = 'settings-status active error';
        status.textContent = formatarDetalheErro(err.message);
    } finally {
        toggle.disabled = false;
    }
}

function _renderLlmMode(data) {
    const valor = document.getElementById('llmModeAtual');
    const modelo = document.getElementById('llmModeModelo');
    const toggle = document.getElementById('llmModeToggle');

    valor.textContent = data.modo === 'local' ? 'Local (Ollama)' : 'Online (Claude)';
    modelo.textContent = `Modelo: ${data.modo === 'local' ? data.modelo_local : data.modelo_online}`;
    toggle.checked = data.modo === 'local';
    toggle.disabled = false;
}


// ============ Helpers locais ============
function formatarHora(iso) {
    try {
        return new Date(iso).toLocaleString('pt-PT', {
            day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
    } catch {
        return iso || '-';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

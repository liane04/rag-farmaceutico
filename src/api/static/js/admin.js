// Vistas exclusivas do admin: documentos (com upload) e auditoria.
// Cada vista renderiza-se num container e tem o seu proprio loader.

import { apiFetch, apiGet, apiPostForm, formatarDetalheErro } from './api.js';

// ============ Vista: Documentos + Upload ============
export function renderDocumentos(container) {
    container.innerHTML = `
        <div class="container">
            <div class="upload-card">
                <div class="upload-title">Adicionar Documento</div>
                <div class="upload-form">
                    <div class="upload-field">
                        <label>Ficheiro PDF</label>
                        <input type="file" class="upload-file-input" id="uploadFile" accept=".pdf">
                    </div>
                    <div class="upload-field">
                        <label>Tipo de documento</label>
                        <select class="upload-select" id="uploadTipo">
                            <option value="bula">Bula</option>
                            <option value="monografia">Monografia</option>
                            <option value="guideline">Guideline</option>
                            <option value="norma">Norma</option>
                        </select>
                    </div>
                    <button class="upload-btn" id="uploadBtn">Enviar e Indexar</button>
                </div>
                <div class="upload-status" id="uploadStatus"></div>
            </div>

            <div class="stats-bar">
                <div class="stat-card">
                    <div class="stat-value" id="statDocs2">-</div>
                    <div class="stat-label">Total Documentos</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="statChunks2">-</div>
                    <div class="stat-label">Total Chunks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="statPaginas">-</div>
                    <div class="stat-label">Total Paginas</div>
                </div>
            </div>
            <div class="docs-grid" id="docsGrid">
                <div class="audit-empty">A carregar documentos...</div>
            </div>
        </div>
    `;
    document.getElementById('uploadBtn').addEventListener('click', uploadDocument);
    loadDocumentos();
}

async function uploadDocument() {
    const fileInput = document.getElementById('uploadFile');
    const tipo = document.getElementById('uploadTipo').value;
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
        const aviso = perdidos > 0 ? ` &#9888; ${perdidos} chunk(s) nao foram indexados.` : '';
        status.className = 'upload-status active success';
        status.innerHTML = `&#10003; Documento indexado: ${data.chunks_gerados} chunks gerados, ${data.pontos_indexados} indexados, ${data.total_na_collection} pontos totais.${aviso}`;

        fileInput.value = '';
        loadDocumentos();
    } catch (err) {
        status.className = 'upload-status active error';
        status.innerHTML = `&#9888; ${err.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Enviar e Indexar';
    }
}

async function loadDocumentos() {
    const grid = document.getElementById('docsGrid');
    try {
        const data = await apiGet('/documentos');

        document.getElementById('statDocs2').textContent = data.total_documentos;
        document.getElementById('statChunks2').textContent = data.total_chunks;

        let totalPaginas = 0;
        data.documentos.forEach(d => totalPaginas += d.paginas.length);
        document.getElementById('statPaginas').textContent = totalPaginas;

        if (data.documentos.length === 0) {
            grid.innerHTML = '<div class="audit-empty">Nenhum documento indexado.</div>';
            return;
        }

        grid.innerHTML = '';
        data.documentos.forEach(doc => {
            const typeClass = 'doc-type-' + (doc.tipo_documento || 'desconhecido');
            const card = document.createElement('div');
            card.className = 'doc-card';
            card.innerHTML = `
                <div class="doc-card-header">
                    <span class="doc-name">${escapeHtml(doc.ficheiro)}</span>
                    <span class="doc-type-badge ${typeClass}">${escapeHtml(doc.tipo_documento)}</span>
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
            `;
            grid.appendChild(card);
        });
    } catch (err) {
        grid.innerHTML = `<div class="audit-empty">Erro ao carregar documentos: ${escapeHtml(err.message)}</div>`;
    }
}

// ============ Vista: Auditoria (todas as consultas) ============
export function renderAuditoria(container) {
    container.innerHTML = `
        <div class="container">
            <div class="audit-controls">
                <span class="audit-title">Historico de Consultas (todos os utilizadores)</span>
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
                            <th>Duracao</th>
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
                : '<span class="audit-user audit-user-anon">(anonimo)</span>';

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

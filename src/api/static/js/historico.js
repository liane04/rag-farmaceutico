// Vista do historico de consultas do farmaceutico autenticado.
// Le do endpoint /historico (filtrado por utilizador no backend).

import { apiGet } from './api.js';

export function renderHistorico(container) {
    container.innerHTML = `
        <div class="container">
            <div class="audit-controls">
                <span class="audit-title">As suas consultas anteriores</span>
                <div style="display:flex; gap:0.5rem; align-items:center;">
                    <span class="audit-count" id="historicoCount">0 registos</span>
                    <button class="search-btn" id="historicoRefreshBtn" style="padding:0.5rem 1rem; font-size:0.8rem;">Atualizar</button>
                </div>
            </div>
            <div class="audit-table-wrapper">
                <table class="audit-table">
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Pergunta</th>
                            <th>Fontes</th>
                            <th>Contexto</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="historicoBody">
                        <tr>
                            <td colspan="5" class="audit-empty">A carregar...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;
    document.getElementById('historicoRefreshBtn').addEventListener('click', carregarHistorico);
    carregarHistorico();
}

async function carregarHistorico() {
    const body = document.getElementById('historicoBody');
    try {
        const data = await apiGet('/historico');

        document.getElementById('historicoCount').textContent = `${data.total} registos`;

        if (data.total === 0) {
            body.innerHTML = '<tr><td colspan="5" class="audit-empty">Ainda nao fez nenhuma consulta.</td></tr>';
            return;
        }

        body.innerHTML = '';
        data.registos.forEach((reg, i) => {
            const data_ = formatarData(reg.timestamp);
            const fontes = (reg.fontes || []).map(f =>
                `<span class="audit-source-mini">${escapeHtml(f.ficheiro || '?')}</span>`
            ).join('');
            const ctxClass = reg.contexto_suficiente ? 'audit-context-ok' : 'audit-context-warn';
            const ctxText = reg.contexto_suficiente ? 'OK' : 'Limitado';

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="audit-time">${data_}</td>
                <td class="audit-query" title="${escapeHtml(reg.query_original)}">${escapeHtml(reg.query_original)}</td>
                <td><div class="audit-sources">${fontes}</div></td>
                <td><span class="audit-context-badge ${ctxClass}">${ctxText}</span></td>
                <td><button class="audit-expand-btn" data-idx="${i}">Ver resposta</button></td>
            `;
            body.appendChild(tr);

            const detailTr = document.createElement('tr');
            detailTr.id = `historico-detail-${i}`;
            detailTr.style.display = 'none';
            detailTr.innerHTML = `
                <td colspan="5" style="padding:0;">
                    <div style="padding:1rem 1.25rem; background:#f8fafc; border-top:1px solid var(--border);">
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
                const row = document.getElementById(`historico-detail-${idx}`);
                row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
            });
        });
    } catch (err) {
        body.innerHTML = `<tr><td colspan="5" class="audit-empty">Erro ao carregar historico: ${escapeHtml(err.message)}</td></tr>`;
    }
}

function formatarData(iso) {
    try {
        return new Date(iso).toLocaleString('pt-PT', {
            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
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

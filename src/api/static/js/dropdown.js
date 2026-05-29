// Custom select component. Substitui o <select> nativo do HTML (que tem o
// popup renderizado pelo SO e nao se consegue estilizar) por uma estrutura
// que pode ser totalmente customizada em CSS.
//
// O HTML esperado para cada select:
//   <div class="custom-select" id="X" data-value="bula">
//       <button type="button" class="custom-select-button" aria-haspopup="listbox" aria-expanded="false">
//           <span class="custom-select-label">Bula</span>
//           <svg class="custom-select-chevron">...</svg>
//       </button>
//       <ul class="custom-select-menu" role="listbox" hidden>
//           <li class="custom-select-option" data-value="bula" role="option">Bula</li>
//           ...
//       </ul>
//   </div>

export function mountCustomSelect(container) {
    const button = container.querySelector('.custom-select-button');
    const menu = container.querySelector('.custom-select-menu');
    const label = container.querySelector('.custom-select-label');
    const options = Array.from(container.querySelectorAll('.custom-select-option'));

    function abrir() {
        // Garante que apenas um dropdown esta aberto de cada vez.
        document.querySelectorAll('.custom-select-menu:not([hidden])').forEach(m => {
            if (m !== menu) m.hidden = true;
        });
        document.querySelectorAll('.custom-select-button[aria-expanded="true"]').forEach(b => {
            if (b !== button) b.setAttribute('aria-expanded', 'false');
        });
        menu.hidden = false;
        button.setAttribute('aria-expanded', 'true');
        posicionarMenu();
    }

    // Decide se o menu abre para baixo (default) ou para cima (quando o
    // botao esta perto do fundo da viewport e o menu nao caberia abaixo).
    // Necessario porque o menu vive dentro de containers com overflow:hidden,
    // entao um menu que extravase pela base e cortado.
    function posicionarMenu() {
        menu.classList.remove('custom-select-menu--top');
        const rect = button.getBoundingClientRect();
        const menuHeight = menu.offsetHeight;
        const margem = 12;
        const espacoAbaixo = window.innerHeight - rect.bottom;
        const espacoAcima = rect.top;
        if (espacoAbaixo < menuHeight + margem && espacoAcima > espacoAbaixo) {
            menu.classList.add('custom-select-menu--top');
        }
    }

    function fechar() {
        menu.hidden = true;
        button.setAttribute('aria-expanded', 'false');
    }

    function selecionar(opt) {
        container.dataset.value = opt.dataset.value || '';
        label.textContent = opt.textContent.trim();
        options.forEach(o => o.classList.toggle('selected', o === opt));
        fechar();
        container.dispatchEvent(new CustomEvent('change', {
            detail: { value: container.dataset.value }
        }));
    }

    button.addEventListener('click', (e) => {
        e.stopPropagation();
        if (menu.hidden) abrir(); else fechar();
    });

    options.forEach(opt => {
        opt.addEventListener('click', () => selecionar(opt));
    });

    // Fechar ao clicar fora ou ao premir Escape.
    document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) fechar();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !menu.hidden) fechar();
    });

    // Marca a opcao inicial conforme data-value.
    const initialValue = container.dataset.value || '';
    const initialOpt = options.find(o => (o.dataset.value || '') === initialValue);
    if (initialOpt) initialOpt.classList.add('selected');
}

export function getCustomSelectValue(container) {
    return container.dataset.value || '';
}

export function setCustomSelectValue(container, value) {
    const options = Array.from(container.querySelectorAll('.custom-select-option'));
    const opt = options.find(o => (o.dataset.value || '') === (value || ''));
    if (!opt) return;
    container.dataset.value = opt.dataset.value || '';
    container.querySelector('.custom-select-label').textContent = opt.textContent.trim();
    options.forEach(o => o.classList.toggle('selected', o === opt));
}

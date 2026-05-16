// =========================================================
// 1. CONFIGURAÇÃO E VARIÁVEIS GLOBAIS
// =========================================================
const API_URL = "https://mercadopago-final.onrender.com/api/cobrancas";
const VALIDAR_CUPOM_URL = "https://mercadopago-final.onrender.com/api/validar-cupom";
 
// Elementos do Modal de Checkout
const checkoutModal = document.getElementById('checkout-modal');
const checkoutModalClose = document.getElementById('checkout-modal-close');
const checkoutProdutoDetalhes = document.getElementById('checkout-produto-detalhes');
const checkoutForm = document.getElementById('checkout-form');
const checkoutResultado = document.getElementById('checkout-resultado');
const checkoutProductIdInput = document.getElementById('checkout_product_id');
const checkoutNomeInput = document.getElementById('checkout_nome');
const checkoutEmailInput = document.getElementById('checkout_email');
const checkoutTelefoneInput = document.getElementById('checkout_telefone');
const checkoutCupomInput = document.getElementById('checkout_cupom'); // NOVO
const checkoutCupomIdInput = document.getElementById('checkout_cupom_id'); // NOVO
const btnAplicarCupom = document.getElementById('btn-aplicar-cupom'); // NOVO
const cupomStatus = document.getElementById('cupom-status'); // NOVO
const precoResumo = document.getElementById('preco-resumo'); // NOVO
const feedbackToast = document.getElementById('feedback-toast');
const checkoutUsuarioIdInput = document.getElementById('checkout_usuario_id'); // NOVOtestemoeda
 
// Elementos do Modo Spotlight (Foco)
const mainStore = document.getElementById('main-store');
const spotlightContainer = document.getElementById('spotlight-container');
 
// Variáveis de estado do cupom
let cupomAplicado = null;
let valorOriginal = 0;
let valorFinal = 0;
 
// =========================================================
// 2. FUNÇÕES DE UI (Modal, Toast, Erros)
// =========================================================
 
function showFieldError(fieldElement, message) {
    if (!fieldElement) return;
    const errorDiv = fieldElement.nextElementSibling; 
    if (errorDiv && errorDiv.classList.contains('field-error')) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }
    fieldElement.style.borderColor = '#e74c3c'; 
}
 
function clearFieldErrors(form) {
    if (!form) return;
    form.querySelectorAll('.field-error').forEach(div => {
        div.textContent = '';
        div.style.display = 'none';
    });
    form.querySelectorAll('input').forEach(input => {
        input.style.borderColor = '#ccc'; 
    });
}
 
function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}
 
function isValidTelefone(telefone) {
    const numeros = telefone.replace(/\D/g, '');
    return numeros.length >= 10 && numeros.length <= 11;
}
 
function aplicarMascaraTelefone(input) {
    input.addEventListener('input', function(e) {
        let valor = e.target.value.replace(/\D/g, '');
        
        if (valor.length > 11) {
            valor = valor.slice(0, 11);
        }
        
        if (valor.length > 7) {
            valor = `(${valor.slice(0, 2)}) ${valor.slice(2, 7)}-${valor.slice(7)}`;
        } else if (valor.length > 2) {
            valor = `(${valor.slice(0, 2)}) ${valor.slice(2)}`;
        } else if (valor.length > 0) {
            valor = `(${valor}`;
        }
        
        e.target.value = valor;
    });
}
 
function showToast(message, type = 'info') {
    if (!feedbackToast) return;
 
    const toastIcon = feedbackToast.querySelector('.toast-icon i');
    const toastMessage = feedbackToast.querySelector('.toast-message');
 
    let iconClass, color;
    switch (type) {
        case 'success': iconClass = 'fas fa-check-circle'; color = '#27ae60'; break;
        case 'error': iconClass = 'fas fa-exclamation-circle'; color = '#e74c3c'; break;
        default: iconClass = 'fas fa-info-circle'; color = '#3498db'; break;
    }
 
    if (toastIcon) toastIcon.className = iconClass;
    if (toastMessage) toastMessage.textContent = message;
    feedbackToast.style.background = color;
    
    feedbackToast.classList.add('show');
    feedbackToast.style.display = 'flex';
 
    setTimeout(() => {
        feedbackToast.classList.remove('show');
        feedbackToast.style.display = 'none';
    }, 5000);
}
 
// =========================================================
// 3. LÓGICA DE CUPOM (NOVO)
// =========================================================
 
async function aplicarCupom() {
    const codigo = checkoutCupomInput.value.trim().toUpperCase();
    const productId = checkoutProductIdInput.value;
    
    if (!codigo) {
        mostrarStatusCupom('Digite um código de cupom', 'erro');
        return;
    }
    
    if (!productId) {
        mostrarStatusCupom('Erro: Produto não identificado', 'erro');
        return;
    }
    
    btnAplicarCupom.disabled = true;
    btnAplicarCupom.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    
    try {
        const response = await fetch(VALIDAR_CUPOM_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                codigo: codigo,
                produto_id: parseInt(productId),
                valor_original: valorOriginal
            })
        });
        
        const result = await response.json();
        
        if (response.ok && result.status === 'success') {
            // Cupom válido!
            cupomAplicado = result.cupom;
            valorFinal = result.calculo.valor_final;
            
            // Salva o ID do cupom no input hidden
            checkoutCupomIdInput.value = result.cupom.id;
            
            // Mostra o resumo de preços
            mostrarResumoPrecos(result.calculo);
            mostrarStatusCupom(`Cupom ${result.cupom.codigo} aplicado! ${result.cupom.descricao}`, 'sucesso');
            
            // Desabilita o input e muda o botão
            checkoutCupomInput.disabled = true;
            btnAplicarCupom.innerHTML = '<i class="fas fa-check"></i> Aplicado';
            btnAplicarCupom.style.background = '#27ae60';
            btnAplicarCupom.style.color = 'white';
            btnAplicarCupom.style.borderColor = '#27ae60';
            
            showToast(`Desconto de ${result.cupom.descricao} aplicado!`, 'success');
        } else {
            // Cupom inválido
            mostrarStatusCupom(result.message || 'Cupom inválido', 'erro');
            btnAplicarCupom.innerHTML = 'Aplicar';
            btnAplicarCupom.disabled = false;
        }
        
    } catch (error) {
        console.error('Erro ao validar cupom:', error);
        mostrarStatusCupom('Erro ao verificar cupom. Tente novamente.', 'erro');
        btnAplicarCupom.innerHTML = 'Aplicar';
        btnAplicarCupom.disabled = false;
    }
}
 
function mostrarStatusCupom(mensagem, tipo) {
    cupomStatus.textContent = mensagem;
    cupomStatus.className = 'cupom-status ' + tipo;
    
    if (tipo === 'sucesso') {
        cupomStatus.innerHTML = '<i class="fas fa-check-circle"></i> ' + mensagem;
    } else if (tipo === 'erro') {
        cupomStatus.innerHTML = '<i class="fas fa-times-circle"></i> ' + mensagem;
    }
}
 
function mostrarResumoPrecos(calculo) {
    precoResumo.style.display = 'block';
    
    document.getElementById('preco-original').textContent = `R$ ${calculo.valor_original.toFixed(2).replace('.', ',')}`;
    document.getElementById('valor-desconto').textContent = `-R$ ${calculo.desconto.toFixed(2).replace('.', ',')} (${Math.round(calculo.percentual_aplicado)}%)`;
    document.getElementById('preco-final').innerHTML = `R$ ${calculo.valor_final.toFixed(2).replace('.', ',')} <span class="tag-desconto">-${Math.round(calculo.percentual_aplicado)}%</span>`;
}
 
function resetarCupom() {
    cupomAplicado = null;
    valorFinal = valorOriginal;
    checkoutCupomIdInput.value = '';
    checkoutCupomInput.value = '';
    checkoutCupomInput.disabled = false;
    
    btnAplicarCupom.innerHTML = 'Aplicar';
    btnAplicarCupom.disabled = false;
    btnAplicarCupom.style.background = 'transparent';
    btnAplicarCupom.style.color = 'var(--orange-web)';
    btnAplicarCupom.style.borderColor = 'var(--orange-web)';
    
    cupomStatus.textContent = '';
    cupomStatus.className = 'cupom-status';
    precoResumo.style.display = 'none';
}
 
// =========================================================
// 4. LÓGICA DE CHECKOUT (Modal e API)
// =========================================================
 
function openCheckoutModal(productId, nome, preco) {
    resetCheckoutModal(); 
    resetarCupom();
 
    valorOriginal = parseFloat(preco);
    valorFinal = valorOriginal;
    
    const precoFormatado = valorOriginal.toFixed(2).replace('.', ',');
    
    checkoutProdutoDetalhes.innerHTML = `
        <h3 style="margin: 0.5rem 0; color: var(--white);">${nome || 'Produto'}</h3>
        <p class="checkout-preco" style="font-size: 1.4rem; font-weight: bold; color: var(--orange-web);">R$ ${precoFormatado}</p>
    `;
    
    checkoutProductIdInput.value = productId;
    
    // --- NOVO: pré-preenche o campo usuario_id para testes ---
    if (checkoutUsuarioIdInput) {
        checkoutUsuarioIdInput.value = '22222222-2222-2222-2222-222222222222';
    }
    // ---------------------------------------------------------
    
    checkoutModal.style.display = 'block';
}
 
function closeCheckoutModal() {
    checkoutModal.style.display = 'none';
    resetCheckoutModal(); 
    if (checkoutUsuarioIdInput) checkoutUsuarioIdInput.value = '';
}
 
function resetCheckoutModal() {
    checkoutProdutoDetalhes.innerHTML = '';
    checkoutResultado.innerHTML = '';
    if (checkoutForm) {
       checkoutForm.reset(); 
       checkoutForm.style.display = 'block'; 
       clearFieldErrors(checkoutForm); 
    }
    if (checkoutUsuarioIdInput) checkoutUsuarioIdInput.value = ''; // NOVO
}
 
async function handleCheckoutSubmit(event) {
    event.preventDefault(); 
    
    if (!validateCheckoutForm()) return;
 
    const nomeCliente = checkoutNomeInput.value;
    const emailCliente = checkoutEmailInput.value;
    const telefoneCliente = checkoutTelefoneInput.value;
    const productId = checkoutProductIdInput.value;
    const cupomId = checkoutCupomIdInput.value; // Pega o ID do cupom se houver
 
    const usuarioId = checkoutUsuarioIdInput?.value || null; // NOVO
 
const dadosParaEnvio = {
    email: emailCliente,
    nome: nomeCliente,
    telefone: telefoneCliente,
    product_id: parseInt(productId),
    cupom_id: cupomId ? parseInt(cupomId) : null,
    usuario_id: currentUsuarioId // <-- usando a variável global
};
 
    showLoadingInCheckoutResult();
    checkoutForm.style.display = 'none'; 
 
    try {
        const response = await fetch(API_URL, { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dadosParaEnvio),
        });
 
        const result = await response.json();
 
        if (response.ok) {
            showQrCodeInCheckoutResult(result);
            
            // Mensagem personalizada se teve desconto
            if (result.desconto_aplicado) {
                showToast(`PIX gerado com ${result.desconto_aplicado.cupom_codigo}! Economia de R$ ${result.desconto_aplicado.valor_desconto.toFixed(2)}`, 'success');
            } else {
                showToast('Cobrança PIX gerada! Verifique os dados.', 'success');
            }
        } else {
            throw new Error(result.message || 'Erro ao gerar cobrança.');
        }
 
    } catch (error) {
        console.error('Erro no checkout:', error);
        showErrorInCheckoutResult(error.message);
        showToast('Erro ao processar. Tente novamente.', 'error');
        checkoutForm.style.display = 'block'; 
    }
}
 
function validateCheckoutForm() {
    clearFieldErrors(checkoutForm); 
    let isValid = true;
    const nome = checkoutNomeInput.value.trim();
    const email = checkoutEmailInput.value.trim();
    const telefone = checkoutTelefoneInput.value.trim();
 
    if (nome.length < 2) {
        showFieldError(checkoutNomeInput, 'Nome muito curto');
        isValid = false;
    }
    if (!email || !isValidEmail(email)) {
        showFieldError(checkoutEmailInput, 'Email inválido');
        isValid = false;
    }
    if (!telefone || !isValidTelefone(telefone)) {
        showFieldError(checkoutTelefoneInput, 'Telefone inválido');
        isValid = false;
    }
    return isValid;
}
 
function showLoadingInCheckoutResult() {
    checkoutResultado.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div class="loading-spinner" style="display:block"></div>
            <p style="margin-top: 1rem; color: #ccc;">Gerando PIX${cupomAplicado ? ' com desconto...' : '...'}</p>
        </div>
    `;
}
 
function showQrCodeInCheckoutResult(data) {
    let descontoHtml = '';
    
    // Se teve desconto, mostra no resultado
    if (data.desconto_aplicado) {
        descontoHtml = `
            <div style="background: rgba(39, 174, 96, 0.1); border: 1px solid #27ae60; border-radius: 8px; padding: 10px; margin-bottom: 15px;">
                <p style="color: #27ae60; margin: 0; font-size: 0.9rem;">
                    <i class="fas fa-tag"></i> Cupom ${data.desconto_aplicado.cupom_codigo} aplicado!<br>
                    <small>Você economizou R$ ${data.desconto_aplicado.valor_desconto.toFixed(2).replace('.', ',')}</small>
                </p>
            </div>
        `;
    }
    
    checkoutResultado.innerHTML = `
        <div style="text-align: center;">
            <h2 style="color: #27ae60; margin-bottom: 1rem;"><i class="fas fa-check-circle"></i> Pague com PIX!</h2>
            ${descontoHtml}
            <div style="background: #fff; padding: 10px; border-radius: 8px; display:inline-block; margin: 10px 0;">
                <img src="data:image/jpeg;base64,${data.qr_code_base64}" alt="QR Code" style="max-width: 100%; display:block;">
            </div>
            <p style="margin: 10px 0; font-weight: bold; color: #fff;">Copia e Cola:</p>
            <textarea readonly onclick="this.select(); document.execCommand('copy'); showToast('Copiado!', 'success');" 
                style="width: 100%; height: 80px; font-size: 0.8rem; padding: 5px; border-radius: 5px; color: #000;">${data.qr_code_text}</textarea>
            <p style="margin-top: 10px; font-size: 0.9rem; color: #bbb;">O produto chegará no seu e-mail após o pagamento.</p>
        </div>
    `;
}
 
function showErrorInCheckoutResult(message) {
      checkoutResultado.innerHTML = `<p style="color: #e74c3c; text-align: center;">${message}</p>`;
}
 
// =========================================================
// =========================================================
// 5. INICIALIZAÇÃO E CONTROLE DE MODO (SPOTLIGHT vs LOJA)
// =========================================================
 
// Variável global para armazenar o usuario_id vindo da URL
let currentUsuarioId = null;
 
document.addEventListener('DOMContentLoaded', () => {
    
    // Aplica máscara no campo de telefone
    if (checkoutTelefoneInput) {
        aplicarMascaraTelefone(checkoutTelefoneInput);
    }
 
    // Evento do botão de aplicar cupom
    if (btnAplicarCupom) {
        btnAplicarCupom.addEventListener('click', aplicarCupom);
    }
    
    // Permite aplicar cupom com Enter
    if (checkoutCupomInput) {
        checkoutCupomInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                aplicarCupom();
            }
        });
    }
 
    // --- Lógica do MODO FOCO (Spotlight) ---
    const params = new URLSearchParams(window.location.search);
    const urlProductId = params.get('id');
    currentUsuarioId = params.get('usuario_id'); // Captura o usuario_id da URL
 
    if (urlProductId) {
        activateSpotlightMode(urlProductId);
    } else {
        initStoreButtons();
    }
 
    // Configura eventos globais (Modal e Form)
    if (checkoutModalClose) checkoutModalClose.addEventListener('click', closeCheckoutModal);
    
    window.addEventListener('click', (event) => {
        if (event.target == checkoutModal) closeCheckoutModal();
    });
 
    if (checkoutForm) checkoutForm.addEventListener('submit', handleCheckoutSubmit);
    
    if (feedbackToast) {
        feedbackToast.addEventListener('click', () => {
            feedbackToast.classList.remove('show');
            feedbackToast.style.display = 'none';
        });
    }
});
 
async function activateSpotlightMode(id) {
    // Sempre busca o preço atualizado do Supabase (ignora card HTML que pode estar desatualizado)
    let produto = null;
 
    try {
        const SUPABASE_URL  = 'https://gyepvrzkwesohbagpgfa.supabase.co';
        const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5ZXB2cnprd2Vzb2hiYWdwZ2ZhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEzMDk5OTAsImV4cCI6MjA3Njg4NTk5MH0.ePwzEE8FjikLiTyjbtJXUtIIwFRlaSf5RYe7iKMDnTA';
        const sb = window.supabase
            ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON)
            : null;
 
        if (sb) {
            const { data } = await sb
                .from('products')
                .select('title, price, image_url, descricao, author, paginas, intro, sobre_autor')
                .eq('id', id)
                .single();
 
            if (data) {
                produto = {
                    img:        data.image_url || '',
                    name:       data.title,
                    price:      String(data.price),
                    desc:       data.descricao   || '',
                    autor:      data.author       || '',
                    paginas:    data.paginas ? String(data.paginas) : '',
                    intro:      data.intro        || '',
                    sobreAutor: data.sobre_autor  || '',
                };
            }
        }
    } catch(e) {
        console.warn('Erro ao buscar produto no Supabase:', e);
        // Fallback: usa dados do card HTML se Supabase falhar
        const sourceCard = document.querySelector(`.book-card[data-id="${id}"]`);
        if (sourceCard) {
            produto = {
                img:        sourceCard.dataset.img,
                name:       sourceCard.dataset.name,
                price:      sourceCard.dataset.price,
                desc:       sourceCard.dataset.desc        || '',
                autor:      sourceCard.dataset.autor       || '',
                paginas:    sourceCard.dataset.paginas     || '',
                intro:      sourceCard.dataset.intro       || '',
                sobreAutor: sourceCard.dataset.sobreAutor  || '',
            };
        }
    }
 
    if (produto && mainStore && spotlightContainer) {
        mainStore.style.display = 'none';
        mainStore.classList.add('hidden');
        spotlightContainer.style.display = 'flex';
 
        document.getElementById('spot-img').src = produto.img;
        document.getElementById('spot-title').innerText = produto.name;
        document.getElementById('spot-desc').innerText  = produto.desc;
        document.getElementById('spot-price').innerText = `R$ ${produto.price.replace('.', ',')}`;
 
        // Metadados (autor e páginas)
        const spotMeta        = document.getElementById('spot-meta');
        const spotAutorWrap   = document.getElementById('spot-autor-wrap');
        const spotPaginasWrap = document.getElementById('spot-paginas-wrap');
 
        if (produto.autor) {
            document.getElementById('spot-autor').innerText = `Autor: ${produto.autor}`;
            spotAutorWrap.style.display = 'flex';
        } else {
            spotAutorWrap.style.display = 'none';
        }
 
        if (produto.paginas) {
            document.getElementById('spot-paginas').innerText = `${produto.paginas} páginas`;
            spotPaginasWrap.style.display = 'flex';
        } else {
            spotPaginasWrap.style.display = 'none';
        }
 
        spotMeta.style.display = (produto.autor || produto.paginas) ? 'flex' : 'none';
 
        // Introdução
        const spotIntroWrap = document.getElementById('spot-intro-wrap');
        if (produto.intro) {
            document.getElementById('spot-intro').innerText = produto.intro;
            spotIntroWrap.style.display = 'block';
        } else {
            spotIntroWrap.style.display = 'none';
        }
 
        // Sobre o autor
        const spotSobreAutorWrap = document.getElementById('spot-sobre-autor-wrap');
        if (produto.sobreAutor) {
            document.getElementById('spot-sobre-autor').innerText = produto.sobreAutor;
            spotSobreAutorWrap.style.display = 'block';
        } else {
            spotSobreAutorWrap.style.display = 'none';
        }
 
        document.getElementById('spot-btn').onclick = () => {
            openCheckoutModalSmart(id, produto.name, produto.price, produto.tipo || 'digital', produto.frete || 0);
        };

        // Carrossel para produto físico
        if (produto.tipo === 'fisico') {
            await carregarCarrossel(id, produto.img);
        } else {
            const spotImg  = document.getElementById('spot-img');
            const carrWrap = document.getElementById('carrossel-wrap');
            if (spotImg)  spotImg.style.display  = 'block';
            if (carrWrap) carrWrap.style.display  = 'none';
        }
 
    } else {
        console.warn("Produto não encontrado para o ID:", id);
        initStoreButtons();
    }
}
 
function initStoreButtons() {
    if(mainStore) mainStore.style.display = 'block';
    if(spotlightContainer) spotlightContainer.style.display = 'none';
 
    const buttons = document.querySelectorAll('.comprar-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const card = e.target.closest('.book-card');
            if(card) {
                const id = card.dataset.id;
                const name  = card.dataset.name;
                const price = card.dataset.price;
                const tipo  = card.dataset.tipo  || 'digital';
                const frete = card.dataset.frete || 0;
                openCheckoutModalSmart(id, name, price, tipo, frete);
            }
        });
    });
}

// =========================================================
// 6. PAGAMENTO COM CARTÃO DE CRÉDITO — CORREÇÃO BROOSTORE
// =========================================================
const API_CARTAO_URL = "https://mercadopago-final.onrender.com/api/cobrancas-cartao";
const MP_PUBLIC_KEY = window.MERCADOPAGO_PUBLIC_KEY || "COLE_SUA_PUBLIC_KEY_AQUI";
let mpInstance = null;
let ultimoPaymentMethodId = null;
let ultimoIssuerId = null;

function getMpInstance() {
    if (mpInstance) return mpInstance;
    if (!window.MercadoPago) {
        throw new Error('SDK do Mercado Pago não carregado. Verifique a tag https://sdk.mercadopago.com/js/v2.');
    }
    if (!MP_PUBLIC_KEY || MP_PUBLIC_KEY === 'COLE_SUA_PUBLIC_KEY_AQUI') {
        throw new Error('Public Key do Mercado Pago não configurada no frontend.');
    }
    mpInstance = new MercadoPago(MP_PUBLIC_KEY, { locale: 'pt-BR' });
    return mpInstance;
}

function switchPaymentTab(tab) {
    const pixSection = document.getElementById('pix-section');
    const cartaoSection = document.getElementById('cartao-section');
    const tabPix = document.getElementById('tab-pix');
    const tabCartao = document.getElementById('tab-cartao');
    const cardResultado = document.getElementById('card-resultado');

    if (!pixSection || !cartaoSection || !tabPix || !tabCartao) return;

    if (tab === 'cartao') {
        pixSection.style.display = 'none';
        cartaoSection.style.display = 'block';
        tabPix.classList.remove('active');
        tabCartao.classList.add('active');
        if (cardResultado) {
            cardResultado.className = 'card-resultado';
            cardResultado.style.display = 'none';
            cardResultado.textContent = '';
        }
    } else {
        pixSection.style.display = 'block';
        cartaoSection.style.display = 'none';
        tabCartao.classList.remove('active');
        tabPix.classList.add('active');
    }
}

function formatCardNumber(input) {
    let value = input.value.replace(/\D/g, '').slice(0, 19);
    input.value = value.replace(/(.{4})/g, '$1 ').trim();
    if (value.length >= 6) atualizarDadosCartao(value.slice(0, 6));
}

function formatExpiry(input) {
    let value = input.value.replace(/\D/g, '').slice(0, 4);
    if (value.length >= 3) value = `${value.slice(0, 2)}/${value.slice(2)}`;
    input.value = value;
}

function formatCPF(input) {
    let value = input.value.replace(/\D/g, '').slice(0, 11);
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d)/, '$1.$2');
    value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    input.value = value;
}

function mostrarResultadoCartao(message, type = 'processing') {
    const box = document.getElementById('card-resultado');
    if (!box) return;
    box.textContent = message;
    box.className = `card-resultado ${type}`;
    box.style.display = 'block';
}

function validarFormularioCartao() {
    const numero = document.getElementById('card-number')?.value.replace(/\D/g, '') || '';
    const validade = document.getElementById('card-expiry')?.value || '';
    const cvv = document.getElementById('card-cvv')?.value.replace(/\D/g, '') || '';
    const nome = document.getElementById('card-name')?.value.trim() || '';
    const cpf = document.getElementById('card-cpf')?.value.replace(/\D/g, '') || '';

    if (numero.length < 13) throw new Error('Número do cartão inválido.');
    if (!/^\d{2}\/\d{2}$/.test(validade)) throw new Error('Validade inválida. Use MM/AA.');
    if (cvv.length < 3) throw new Error('CVV inválido.');
    if (nome.length < 3) throw new Error('Nome do titular inválido.');
    if (cpf.length !== 11) throw new Error('CPF do titular inválido.');

    const [mes, anoCurto] = validade.split('/');
    const mesNum = parseInt(mes, 10);
    if (mesNum < 1 || mesNum > 12) throw new Error('Mês de validade inválido.');

    return {
        numero,
        mes,
        ano: `20${anoCurto}`,
        cvv,
        nome,
        cpf
    };
}

async function atualizarDadosCartao(bin) {
    try {
        const mp = getMpInstance();
        const methods = await mp.getPaymentMethods({ bin });
        const paymentMethod = methods?.results?.[0];
        if (!paymentMethod) return;

        ultimoPaymentMethodId = paymentMethod.id;

        const brandImg = document.getElementById('card-brand-img');
        if (brandImg && paymentMethod.thumbnail) {
            brandImg.src = paymentMethod.thumbnail;
            brandImg.style.display = 'block';
        }

        const issuers = await mp.getIssuers({ paymentMethodId: ultimoPaymentMethodId, bin });
        ultimoIssuerId = issuers?.[0]?.id || null;

        const amount = String((valorFinal || valorOriginal || 0).toFixed(2));
        const installments = await mp.getInstallments({ amount, bin, paymentMethodId: ultimoPaymentMethodId });
        const payerCosts = installments?.[0]?.payer_costs || [];
        const select = document.getElementById('card-installments');
        const group = document.getElementById('installments-group');

        if (select && group && payerCosts.length) {
            select.innerHTML = payerCosts.map(cost => {
                const texto = cost.recommended_message || `${cost.installments}x de R$ ${Number(cost.installment_amount).toFixed(2).replace('.', ',')}`;
                return `<option value="${cost.installments}">${texto}</option>`;
            }).join('');
            group.style.display = 'block';
        }
    } catch (error) {
        console.warn('[Cartão] Não foi possível atualizar bandeira/parcelas:', error);
    }
}

async function pagarCartao() {
    const btn = document.getElementById('btn-pagar-cartao');
    try {
        if (!validateCheckoutForm()) return;
        const dadosCartao = validarFormularioCartao();
        const mp = getMpInstance();

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando...';
        mostrarResultadoCartao('Validando cartão com o Mercado Pago...', 'processing');

        if (!ultimoPaymentMethodId) {
            await atualizarDadosCartao(dadosCartao.numero.slice(0, 6));
        }
        if (!ultimoPaymentMethodId) {
            throw new Error('Não foi possível identificar a bandeira do cartão. Confira o número informado.');
        }

        const tokenResponse = await mp.createCardToken({
            cardNumber: dadosCartao.numero,
            cardholderName: dadosCartao.nome,
            cardExpirationMonth: dadosCartao.mes,
            cardExpirationYear: dadosCartao.ano,
            securityCode: dadosCartao.cvv,
            identificationType: 'CPF',
            identificationNumber: dadosCartao.cpf
        });

        const token = tokenResponse?.id;
        if (!token) throw new Error('Não foi possível gerar o token do cartão.');

        const parcelas = document.getElementById('card-installments')?.value || 1;
        const payload = {
            token,
            payment_method_id: ultimoPaymentMethodId,
            issuer_id: ultimoIssuerId,
            installments: parseInt(parcelas, 10) || 1,
            email: checkoutEmailInput.value.trim(),
            nome: checkoutNomeInput.value.trim(),
            cpf: dadosCartao.cpf,
            product_id: parseInt(checkoutProductIdInput.value, 10),
            cupom_id: checkoutCupomIdInput.value ? parseInt(checkoutCupomIdInput.value, 10) : null
        };

        mostrarResultadoCartao('Enviando pagamento...', 'processing');
        const response = await fetch(API_CARTAO_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.message || result.mensagem || 'Pagamento recusado.');
        }

        if (result.status === 'approved') {
            checkoutForm.style.display = 'none';
            checkoutResultado.innerHTML = `<h2 style="color:#27ae60;"><i class="fas fa-check-circle"></i> Pagamento aprovado!</h2><p>${result.mensagem || 'Você receberá o produto por e-mail em instantes.'}</p>`;
            showToast('Pagamento aprovado!', 'success');
        } else if (result.status === 'in_process') {
            mostrarResultadoCartao(result.mensagem || 'Pagamento em análise.', 'processing');
            showToast('Pagamento em análise.', 'info');
        } else {
            mostrarResultadoCartao(result.mensagem || 'Pagamento não aprovado. Verifique os dados.', 'error');
            showToast('Pagamento não aprovado.', 'error');
        }
    } catch (error) {
        console.error('[Cartão] Erro:', error);
        mostrarResultadoCartao(error.message, 'error');
        showToast(error.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-lock"></i> Pagar com Cartão';
        }
    }
}

// Expõe as funções usadas por atributos inline do HTML.
window.switchPaymentTab = switchPaymentTab;
window.formatCardNumber = formatCardNumber;
window.formatExpiry = formatExpiry;
window.formatCPF = formatCPF;
window.pagarCartao = pagarCartao;

// =========================================================
// CHECKOUT FÍSICO — Modal, CEP, PIX e Cartão
// =========================================================

let fisicoValorOriginal = 0;
let fisicoValorFrete    = 0;
let fisicoValorFinal    = 0;
let fisicoCupomAplicado = null;

// ── Abre o modal físico ───────────────────────────────────
function openCheckoutFisicoModal(productId, nome, preco, frete) {
    fisicoValorOriginal = parseFloat(preco)  || 0;
    fisicoValorFrete    = parseFloat(frete)  || 0;
    fisicoValorFinal    = fisicoValorOriginal + fisicoValorFrete;
    fisicoCupomAplicado = null;

    const precoFmt = fisicoValorOriginal.toFixed(2).replace('.', ',');

    document.getElementById('fisico-produto-detalhes').innerHTML = `
        <h3 style="margin:.5rem 0;color:#fff;">📦 ${nome}</h3>
        <p style="font-size:1.3rem;font-weight:bold;color:var(--orange-web,#fca311);">R$ ${precoFmt}</p>
        <p style="font-size:.82rem;color:#888;margin-top:.3rem;">
            <i class="fas fa-truck"></i> Frete: R$ ${fisicoValorFrete.toFixed(2).replace('.', ',')}
        </p>
    `;

    document.getElementById('fisico_product_id').value = productId;
    atualizarResumoFisico();
    switchFisicoTab('pix');

    const modal = document.getElementById('checkout-fisico-modal');
    modal.style.display = 'block';
}

function closeCheckoutFisicoModal() {
    document.getElementById('checkout-fisico-modal').style.display = 'none';
    resetCheckoutFisicoModal();
}

function resetCheckoutFisicoModal() {
    const form = document.getElementById('checkout-fisico-form');
    if (form) form.reset();
    document.getElementById('fisico-resultado').innerHTML = '';
    document.getElementById('fisico-cupom-status').textContent = '';
    const btnCupom = document.getElementById('fisico-btn-cupom');
    if (btnCupom) { btnCupom.disabled = false; btnCupom.textContent = 'Aplicar'; btnCupom.style.cssText = ''; }
    fisicoValorOriginal = 0; fisicoValorFrete = 0; fisicoValorFinal = 0; fisicoCupomAplicado = null;
}

// ── Abas PIX / Cartão (mesmo padrão do modal digital) ────
function switchFisicoTab(tab) {
    const pixSec    = document.getElementById('fisico-pix-section');
    const cartSec   = document.getElementById('fisico-cartao-section');
    const tabPix    = document.getElementById('fisico-tab-pix');
    const tabCart   = document.getElementById('fisico-tab-cartao');
    if (tab === 'cartao') {
        pixSec.style.display  = 'none';
        cartSec.style.display = 'block';
        tabPix.classList.remove('active');
        tabCart.classList.add('active');
    } else {
        pixSec.style.display  = 'block';
        cartSec.style.display = 'none';
        tabPix.classList.add('active');
        tabCart.classList.remove('active');
    }
}

// ── Busca CEP automaticamente via ViaCEP ─────────────────
async function buscarCEP(input) {
    let v = input.value.replace(/\D/g, '').slice(0, 8);
    input.value = v.length > 5 ? v.slice(0,5) + '-' + v.slice(5) : v;
    if (v.length !== 8) return;
    try {
        const r = await fetch(`https://viacep.com.br/ws/${v}/json/`);
        const d = await r.json();
        if (!d.erro) {
            document.getElementById('fisico_rua').value    = d.logradouro || '';
            document.getElementById('fisico_bairro').value = d.bairro     || '';
            document.getElementById('fisico_cidade').value = d.localidade || '';
            document.getElementById('fisico_estado').value = d.uf         || '';
            document.getElementById('fisico_numero').focus();
        }
    } catch(e) { console.warn('CEP não encontrado', e); }
}

// ── Resumo de preços ──────────────────────────────────────
function atualizarResumoFisico() {
    const sub   = fisicoCupomAplicado
        ? (fisicoValorOriginal - fisicoCupomAplicado.desconto)
        : fisicoValorOriginal;
    fisicoValorFinal = sub + fisicoValorFrete;

    document.getElementById('fisico-subtotal').textContent =
        `R$ ${sub.toFixed(2).replace('.', ',')}`;
    document.getElementById('fisico-frete-valor').textContent =
        `R$ ${fisicoValorFrete.toFixed(2).replace('.', ',')}`;
    document.getElementById('fisico-total').textContent =
        `R$ ${fisicoValorFinal.toFixed(2).replace('.', ',')}`;
}

// ── Cupom no modal físico ─────────────────────────────────
async function aplicarCupomFisico() {
    const codigo    = document.getElementById('fisico_cupom').value.trim().toUpperCase();
    const productId = document.getElementById('fisico_product_id').value;
    const statusEl  = document.getElementById('fisico-cupom-status');
    const btn       = document.getElementById('fisico-btn-cupom');
    if (!codigo) { statusEl.textContent = 'Digite um código'; statusEl.className = 'cupom-status erro'; return; }
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    try {
        const r = await fetch(VALIDAR_CUPOM_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ codigo, produto_id: parseInt(productId), valor_original: fisicoValorOriginal })
        });
        const d = await r.json();
        if (r.ok && d.status === 'success') {
            fisicoCupomAplicado = { id: d.cupom.id, desconto: fisicoValorOriginal - d.calculo.valor_final };
            document.getElementById('fisico_cupom_id').value = d.cupom.id;
            statusEl.innerHTML = `<i class="fas fa-check-circle"></i> ${d.cupom.descricao}`;
            statusEl.className = 'cupom-status sucesso';
            btn.innerHTML = '<i class="fas fa-check"></i> Aplicado';
            btn.style.cssText = 'background:#27ae60;color:#fff;border-color:#27ae60;';
            document.getElementById('fisico_cupom').disabled = true;
            atualizarResumoFisico();
        } else {
            statusEl.textContent = d.message || 'Cupom inválido';
            statusEl.className = 'cupom-status erro';
            btn.disabled = false; btn.textContent = 'Aplicar';
        }
    } catch(e) {
        statusEl.textContent = 'Erro ao verificar cupom';
        statusEl.className = 'cupom-status erro';
        btn.disabled = false; btn.textContent = 'Aplicar';
    }
}

// ── Valida formulário físico ──────────────────────────────
function validarFormFisico() {
    const campos = [
        { id: 'fisico_nome',    msg: 'Nome obrigatório' },
        { id: 'fisico_email',   msg: 'Email inválido' },
        { id: 'fisico_telefone',msg: 'Telefone obrigatório' },
        { id: 'fisico_cep',     msg: 'CEP obrigatório' },
        { id: 'fisico_rua',     msg: 'Rua obrigatória' },
        { id: 'fisico_numero',  msg: 'Número obrigatório' },
        { id: 'fisico_bairro',  msg: 'Bairro obrigatório' },
        { id: 'fisico_cidade',  msg: 'Cidade obrigatória' },
        { id: 'fisico_estado',  msg: 'Estado obrigatório' },
    ];
    let ok = true;
    campos.forEach(c => {
        const el = document.getElementById(c.id);
        const err = el && el.nextElementSibling;
        if (el && !el.value.trim()) {
            if (err) { err.textContent = c.msg; err.style.display = 'block'; }
            el.style.borderColor = '#e74c3c';
            ok = false;
        } else if (el) {
            if (err) { err.textContent = ''; err.style.display = 'none'; }
            el.style.borderColor = '';
        }
    });
    return ok;
}

// ── Submit PIX (produto físico) ───────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const formFisico = document.getElementById('checkout-fisico-form');
    if (formFisico) {
        formFisico.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!validarFormFisico()) return;

            const endereco = {
                cep:         document.getElementById('fisico_cep').value,
                rua:         document.getElementById('fisico_rua').value,
                numero:      document.getElementById('fisico_numero').value,
                complemento: document.getElementById('fisico_complemento').value,
                bairro:      document.getElementById('fisico_bairro').value,
                cidade:      document.getElementById('fisico_cidade').value,
                estado:      document.getElementById('fisico_estado').value,
            };

            const payload = {
                email:      document.getElementById('fisico_email').value,
                nome:       document.getElementById('fisico_nome').value,
                telefone:   document.getElementById('fisico_telefone').value,
                product_id: parseInt(document.getElementById('fisico_product_id').value),
                cupom_id:   document.getElementById('fisico_cupom_id').value
                            ? parseInt(document.getElementById('fisico_cupom_id').value) : null,
                endereco,
                frete:      fisicoValorFrete,
            };

            const btn = formFisico.querySelector('button[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gerando PIX...';

            const resultEl = document.getElementById('fisico-resultado');

            try {
                const r = await fetch(API_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await r.json();

                if (r.ok) {
                    formFisico.style.display = 'none';
                    resultEl.innerHTML = `
                        <div style="text-align:center;">
                            <h2 style="color:#27ae60;margin-bottom:1rem;">
                                <i class="fas fa-check-circle"></i> Pague com PIX!
                            </h2>
                            <p style="color:#aaa;font-size:.85rem;margin-bottom:1rem;">
                                Após o pagamento, entraremos em contato para confirmar o envio.
                            </p>
                            <div style="background:#fff;padding:10px;border-radius:8px;display:inline-block;margin:10px 0;">
                                <img src="data:image/jpeg;base64,${data.qr_code_base64}"
                                     alt="QR Code" style="max-width:100%;display:block;">
                            </div>
                            <p style="margin:10px 0;font-weight:bold;color:#fff;">Copia e Cola:</p>
                            <textarea readonly onclick="this.select();document.execCommand('copy');showToast('Copiado!','success');"
                                style="width:100%;height:80px;font-size:.8rem;padding:5px;border-radius:5px;color:#000;"
                            >${data.qr_code_text}</textarea>
                        </div>`;
                } else {
                    throw new Error(data.message || 'Erro ao gerar PIX.');
                }
            } catch(err) {
                resultEl.innerHTML = `<p style="color:#e74c3c;text-align:center;">${err.message}</p>`;
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-lock"></i> Gerar QR Code PIX';
            }
        });
    }

    // Fecha modal físico
    const closeBtn = document.getElementById('checkout-fisico-close');
    if (closeBtn) closeBtn.addEventListener('click', closeCheckoutFisicoModal);
    window.addEventListener('click', (e) => {
        const m = document.getElementById('checkout-fisico-modal');
        if (e.target === m) closeCheckoutFisicoModal();
    });
});

// ── Detecta tipo do produto e abre o modal correto ────────
function openCheckoutModalSmart(productId, nome, preco, tipo, frete) {
    if (tipo === 'fisico') {
        openCheckoutFisicoModal(productId, nome, preco, frete);
    } else {
        openCheckoutModal(productId, nome, preco);
    }
}

// ── Pagar com cartão (produto físico) ─────────────────────
async function pagarCartaoFisico() {
    if (!validarFormFisico()) return;
    const btn = document.getElementById('checkout-fisico-modal').querySelector('.btn-pagar-cartao');
    const cardResultado = document.getElementById('fisico-card-resultado');
    cardResultado.className = 'card-resultado processing';
    cardResultado.textContent = 'Validando cartão...';
    cardResultado.style.display = 'block';
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando...';

    const cardNumber = document.getElementById('fisico-card-number').value.replace(/\s/g,'');
    const cardExpiry = document.getElementById('fisico-card-expiry').value;
    const cardCvv    = document.getElementById('fisico-card-cvv').value;
    const cardName   = document.getElementById('fisico-card-name').value;
    const cardCpf    = document.getElementById('fisico-card-cpf').value.replace(/\D/g,'');
    const installments = document.getElementById('fisico-card-installments').value || '1';

    try {
        if (!mp) throw new Error('SDK do Mercado Pago não carregado.');
        const [expMonth, expYear] = cardExpiry.split('/');
        const tokenData = await mp.createCardToken({
            cardNumber, cardholderName: cardName,
            cardExpirationMonth: expMonth,
            cardExpirationYear: expYear.length === 2 ? '20'+expYear : expYear,
            securityCode: cardCvv,
            identificationType: 'CPF', identificationNumber: cardCpf,
        });
        if (!tokenData || !tokenData.id) throw new Error('Não foi possível validar o cartão.');

        let paymentMethodId = '', issuerId = '';
        try {
            const pm = await mp.getPaymentMethods({ bin: cardNumber.slice(0,6) });
            if (pm && pm.results && pm.results[0]) {
                paymentMethodId = pm.results[0].id;
                issuerId = pm.results[0].issuer?.id ? String(pm.results[0].issuer.id) : '';
            }
        } catch(e) {}

        const endereco = {
            cep:         document.getElementById('fisico_cep').value,
            rua:         document.getElementById('fisico_rua').value,
            numero:      document.getElementById('fisico_numero').value,
            complemento: document.getElementById('fisico_complemento').value,
            bairro:      document.getElementById('fisico_bairro').value,
            cidade:      document.getElementById('fisico_cidade').value,
            estado:      document.getElementById('fisico_estado').value,
        };

        const r = await fetch(API_URL_CARTAO, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: tokenData.id, payment_method_id: paymentMethodId,
                issuer_id: issuerId || undefined,
                installments: parseInt(installments),
                email:    document.getElementById('fisico_email').value,
                nome:     document.getElementById('fisico_nome').value,
                cpf:      cardCpf,
                product_id: parseInt(document.getElementById('fisico_product_id').value),
                cupom_id: document.getElementById('fisico_cupom_id').value
                          ? parseInt(document.getElementById('fisico_cupom_id').value) : null,
                endereco, frete: fisicoValorFrete,
            })
        });
        const result = await r.json();

        if (result.status === 'approved') {
            cardResultado.className = 'card-resultado success';
            cardResultado.innerHTML = '<i class="fas fa-check-circle"></i> Pagamento aprovado! Entraremos em contato para confirmar o envio.';
            showToast('Pagamento aprovado!', 'success');
        } else {
            throw new Error(result.mensagem || result.message || 'Pagamento não aprovado.');
        }
    } catch(err) {
        cardResultado.className = 'card-resultado error';
        cardResultado.innerHTML = `<i class="fas fa-times-circle"></i> ${err.message}`;
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-lock"></i> Pagar com Cartão';
    }
}

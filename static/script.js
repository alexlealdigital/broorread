// =========================================================
// 1. CONFIGURAÇÃO E VARIÁVEIS GLOBAIS
// =========================================================
const API_URL = "/api/cobrancas";
const VALIDAR_CUPOM_URL = "/api/validar-cupom";
const CARTAO_API_URL = '/api/cobrancas-cartao';

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
const checkoutCupomInput = document.getElementById('checkout_cupom');
const checkoutCupomIdInput = document.getElementById('checkout_cupom_id');
const btnAplicarCupom = document.getElementById('btn-aplicar-cupom');
const cupomStatus = document.getElementById('cupom-status');
const precoResumo = document.getElementById('preco-resumo');
const feedbackToast = document.getElementById('feedback-toast');
const checkoutUsuarioIdInput = document.getElementById('checkout_usuario_id');

// Elementos do Modo Spotlight (Foco)
const mainStore = document.getElementById('main-store');
const spotlightContainer = document.getElementById('spotlight-container');

// Variáveis de estado do cupom
let cupomAplicado = null;
let valorOriginal = 0;
let valorFinal = 0;

// Captura o usuario_id da URL
const urlParams = new URLSearchParams(window.location.search);
const usuarioIdFromUrl = urlParams.get('usuario_id');

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
// 3. LÓGICA DE CUPOM
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
            cupomAplicado = result.cupom;
            valorFinal = result.calculo.valor_final;
            checkoutCupomIdInput.value = result.cupom.id;
            mostrarResumoPrecos(result.calculo);
            mostrarStatusCupom(`Cupom ${result.cupom.codigo} aplicado! ${result.cupom.descricao}`, 'sucesso');
            checkoutCupomInput.disabled = true;
            btnAplicarCupom.innerHTML = '<i class="fas fa-check"></i> Aplicado';
            btnAplicarCupom.style.background = '#27ae60';
            btnAplicarCupom.style.color = 'white';
            btnAplicarCupom.style.borderColor = '#27ae60';
            showToast(`Desconto de ${result.cupom.descricao} aplicado!`, 'success');
        } else {
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
    if (typeof resetCardForm === 'function') resetCardForm();
    const priceInput = document.getElementById('checkout_product_price');
    if (priceInput) priceInput.value = preco;

    valorOriginal = parseFloat(preco);
    valorFinal = valorOriginal;
    
    const precoFormatado = valorOriginal.toFixed(2).replace('.', ',');
    
    checkoutProdutoDetalhes.innerHTML = `
        <h3 style="margin: 0.5rem 0; color: var(--white);">${nome || 'Produto'}</h3>
        <p class="checkout-preco" style="font-size: 1.4rem; font-weight: bold; color: var(--orange-web);">R$ ${precoFormatado}</p>
    `;
    
    checkoutProductIdInput.value = productId;
    
    // Preenche o campo usuario_id se estiver na URL
    if (checkoutUsuarioIdInput) {
        checkoutUsuarioIdInput.value = usuarioIdFromUrl || '';
    }
    
    checkoutModal.style.display = 'block';
}

function closeCheckoutModal() {
    checkoutModal.style.display = 'none';
    resetCheckoutModal(); 
}

function resetCheckoutModal() {
    checkoutProdutoDetalhes.innerHTML = '';
    checkoutResultado.innerHTML = '';
    if (checkoutForm) {
       checkoutForm.reset(); 
       checkoutForm.style.display = 'block'; 
       clearFieldErrors(checkoutForm); 
    }
}

async function handleCheckoutSubmit(event) {
    event.preventDefault(); 
    
    if (!validateCheckoutForm()) return;

    const submitBtn = checkoutForm.querySelector('.btn-confirmar-pagamento');
    const originalBtnText = submitBtn.innerHTML;
    
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando...';
    
    const payload = {
        nome: checkoutNomeInput.value,
        email: checkoutEmailInput.value,
        telefone: checkoutTelefoneInput.value,
        product_id: checkoutProductIdInput.value,
        cupom_id: checkoutCupomIdInput.value || null,
        usuario_id: checkoutUsuarioIdInput ? checkoutUsuarioIdInput.value : null
    };

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            checkoutForm.style.display = 'none';
            checkoutResultado.innerHTML = `
                <div class="checkout-success">
                    <i class="fas fa-check-circle" style="color: #27ae60; font-size: 3rem; margin-bottom: 1rem;"></i>
                    <h3>Pix Gerado com Sucesso!</h3>
                    <p>Escaneie o QR Code abaixo ou copie o código Pix para pagar.</p>
                    <div style="margin: 1.5rem 0;">
                        <img src="data:image/png;base64,${data.qr_code_base64}" alt="QR Code Pix" style="max-width: 200px;">
                    </div>
                    <label>Código Pix (Copia e Cola):</label>
                    <textarea readonly id="pix-code">${data.qr_code_text}</textarea>
                    <button class="cta-button" onclick="copyPixCode()" style="margin-top: 10px;">
                        <i class="fas fa-copy"></i> Copiar Código
                    </button>
                    <p style="font-size: 0.8rem; margin-top: 1rem; opacity: 0.7;">O produto será enviado para seu e-mail assim que o pagamento for confirmado.</p>
                </div>
            `;
            showToast('Pix gerado com sucesso!', 'success');
        } else {
            showToast(data.message || 'Erro ao gerar Pix.', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        }
    } catch (error) {
        console.error('Erro no checkout:', error);
        showToast('Erro de conexão. Tente novamente.', 'error');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalBtnText;
    }
}

function validateCheckoutForm() {
    clearFieldErrors(checkoutForm);
    let isValid = true;

    if (!checkoutNomeInput.value.trim()) {
        showFieldError(checkoutNomeInput, 'Nome é obrigatório');
        isValid = false;
    }

    if (!isValidEmail(checkoutEmailInput.value)) {
        showFieldError(checkoutEmailInput, 'E-mail inválido');
        isValid = false;
    }

    return isValid;
}

function copyPixCode() {
    const pixCode = document.getElementById('pix-code');
    pixCode.select();
    document.execCommand('copy');
    showToast('Código Pix copiado!', 'success');
}

// Inicialização
document.addEventListener('DOMContentLoaded', () => {
    if (checkoutForm) checkoutForm.addEventListener('submit', handleCheckoutSubmit);
    if (checkoutModalClose) checkoutModalClose.addEventListener('click', closeCheckoutModal);
    if (btnAplicarCupom) btnAplicarCupom.addEventListener('click', aplicarCupom);
    if (checkoutTelefoneInput) aplicarMascaraTelefone(checkoutTelefoneInput);
    initStoreButtons();
});

function initStoreButtons() {
    const buttons = document.querySelectorAll('.comprar-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const card = e.target.closest('.book-card');
            if(card) {
                const id = card.dataset.id;
                const name = card.dataset.name;
                const price = card.dataset.price;
                openCheckoutModal(id, name, price);
            }
        });
    });
}

// Mercado Pago SDK (Cartão)
const MP_PUBLIC_KEY = 'APP_USR-cc363414-8a58-4bf6-8a2f-fd1efda8176e';
let mpInstance = null;

function initMercadoPago() {
    if (typeof MercadoPago !== 'undefined') {
        mpInstance = new MercadoPago(MP_PUBLIC_KEY, { locale: 'pt-BR' });
    }
}
initMercadoPago();

async function pagarCartao() {
    if (!mpInstance) return;

    const btn = document.getElementById('btn-pagar-cartao');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processando...';

    // Lógica simplificada para exemplo (deve seguir a implementação original de captura de campos)
    const payload = {
        token: 'TOKEN_GERADO_PELO_SDK',
        payment_method_id: 'master',
        email: checkoutEmailInput.value,
        nome: checkoutNomeInput.value,
        cpf: document.getElementById('card-cpf').value.replace(/\D/g, ''),
        product_id: checkoutProductIdInput.value,
        usuario_id: checkoutUsuarioIdInput ? checkoutUsuarioIdInput.value : null
    };

    try {
        const resp = await fetch(CARTAO_API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        // Tratar resposta...
    } catch(err) {
        console.error(err);
    }
}

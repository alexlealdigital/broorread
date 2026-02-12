// =========================================================
// 1. CONFIGURAÇÃO E VARIÁVEIS GLOBAIS
// =========================================================
const API_URL = "https://mercadopago-final.onrender.com/api/cobrancas"; 

// Elementos do Modal de Checkout
const checkoutModal = document.getElementById('checkout-modal');
const checkoutModalClose = document.getElementById('checkout-modal-close');
const checkoutProdutoDetalhes = document.getElementById('checkout-produto-detalhes');
const checkoutForm = document.getElementById('checkout-form');
const checkoutResultado = document.getElementById('checkout-resultado');
const checkoutProductIdInput = document.getElementById('checkout_product_id');
const checkoutNomeInput = document.getElementById('checkout_nome');
const checkoutEmailInput = document.getElementById('checkout_email');
const checkoutTelefoneInput = document.getElementById('checkout_telefone'); // NOVO
const feedbackToast = document.getElementById('feedback-toast');

// Elementos do Modo Spotlight (Foco)
const mainStore = document.getElementById('main-store');
const spotlightContainer = document.getElementById('spotlight-container');

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

// NOVO: Validação de telefone brasileiro
function isValidTelefone(telefone) {
    // Remove tudo que não é número
    const numeros = telefone.replace(/\D/g, '');
    // Valida se tem 10 ou 11 dígitos (com ou sem 9)
    return numeros.length >= 10 && numeros.length <= 11;
}

// NOVO: Máscara de telefone
function aplicarMascaraTelefone(input) {
    input.addEventListener('input', function(e) {
        let valor = e.target.value.replace(/\D/g, '');
        
        if (valor.length > 11) {
            valor = valor.slice(0, 11);
        }
        
        // Aplica a máscara (XX) XXXXX-XXXX ou (XX) XXXX-XXXX
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
// 3. LÓGICA DE CHECKOUT (Modal e API)
// =========================================================

function openCheckoutModal(productId, nome, preco) {
    resetCheckoutModal(); 

    // Formata o preço para exibição
    const precoFormatado = typeof preco === 'number' ? preco.toFixed(2).replace('.', ',') : preco.replace('.', ',');
    
    checkoutProdutoDetalhes.innerHTML = `
        <h3 style="margin: 0.5rem 0; color: var(--white);">${nome || 'Produto'}</h3>
        <p class="checkout-preco" style="font-size: 1.4rem; font-weight: bold; color: var(--orange-web);">R$ ${precoFormatado}</p>
    `;
    
    checkoutProductIdInput.value = productId;
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

    const nomeCliente = checkoutNomeInput.value;
    const emailCliente = checkoutEmailInput.value;
    const telefoneCliente = checkoutTelefoneInput.value; // NOVO
    const productId = checkoutProductIdInput.value; 

    const dadosParaEnvio = {
        email: emailCliente,
        nome: nomeCliente,
        telefone: telefoneCliente, // NOVO: Envia telefone para API
        product_id: parseInt(productId) 
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
            showToast('Cobrança PIX gerada! Verifique os dados.', 'success');
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
    const telefone = checkoutTelefoneInput.value.trim(); // NOVO

    if (nome.length < 2) {
        showFieldError(checkoutNomeInput, 'Nome muito curto');
        isValid = false;
    }
    if (!email || !isValidEmail(email)) {
        showFieldError(checkoutEmailInput, 'Email inválido');
        isValid = false;
    }
    // NOVO: Validação do telefone
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
            <p style="margin-top: 1rem; color: #ccc;">Gerando PIX...</p>
        </div>
    `;
}

function showQrCodeInCheckoutResult(data) {
    checkoutResultado.innerHTML = `
        <div style="text-align: center;">
            <h2 style="color: #27ae60; margin-bottom: 1rem;"><i class="fas fa-check-circle"></i> Pague com PIX!</h2>
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
// 4. INICIALIZAÇÃO E CONTROLE DE MODO (SPOTLIGHT vs LOJA)
// =========================================================

document.addEventListener('DOMContentLoaded', () => {
    
    // NOVO: Aplica máscara no campo de telefone
    if (checkoutTelefoneInput) {
        aplicarMascaraTelefone(checkoutTelefoneInput);
    }

    // --- Lógica do MODO FOCO (Spotlight) ---
    const params = new URLSearchParams(window.location.search);
    const urlProductId = params.get('id');

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

function activateSpotlightMode(id) {
    const sourceCard = document.querySelector(`.book-card[data-id="${id}"]`);
    
    if (sourceCard && mainStore && spotlightContainer) {
        mainStore.style.display = 'none'; 
        mainStore.classList.add('hidden');
        
        spotlightContainer.style.display = 'flex';

        const img = sourceCard.dataset.img;
        const name = sourceCard.dataset.name;
        const price = sourceCard.dataset.price;
        const desc = sourceCard.dataset.desc;

        document.getElementById('spot-img').src = img;
        document.getElementById('spot-title').innerText = name;
        document.getElementById('spot-desc').innerText = desc;
        document.getElementById('spot-price').innerText = `R$ ${price.replace('.', ',')}`;

        const spotBtn = document.getElementById('spot-btn');
        spotBtn.onclick = () => {
            openCheckoutModal(id, name, price);
        };
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
                const name = card.dataset.name;
                const price = card.dataset.price;
                openCheckoutModal(id, name, price);
            }
        });
    });
}

// Arquivo: script.js (Atualizado para Checkout com Dropdown de Vendedor)

// --- Seletores Globais ---
const checkoutModal = document.getElementById('checkout-modal');
const checkoutModalClose = document.getElementById('checkout-modal-close');
const checkoutProdutoDetalhes = document.getElementById('checkout-produto-detalhes');
const checkoutForm = document.getElementById('checkout-form');
const checkoutResultado = document.getElementById('checkout-resultado');
const checkoutProductIdInput = document.getElementById('checkout_product_id');
const checkoutNomeInput = document.getElementById('checkout_nome');
const checkoutEmailInput = document.getElementById('checkout_email');
const feedbackToast = document.getElementById('feedback-toast');

// NOVO: Seletor para o Dropdown de Vendedores
const checkoutVendedorSelect = document.getElementById('checkout_vendedor');


// --- FUNÇÕES AUXILIARES DE UI (MODAL E TOAST) ---

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
    const errorDivs = form.querySelectorAll('.field-error');
    errorDivs.forEach(div => {
        div.textContent = '';
        div.style.display = 'none';
    });
    const inputs = form.querySelectorAll('input, textarea, select'); // Inclui select
    inputs.forEach(input => {
        // Reseta a borda para o padrão do input/select
        input.style.borderColor = 'var(--border-grey)'; 
    });
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

function showToast(message, type = 'info') {
    if (!feedbackToast) {
        console.warn("Elemento Toast não encontrado com ID: feedback-toast");
        return; 
    }

    const toastIcon = feedbackToast.querySelector('.toast-icon i');
    const toastMessage = feedbackToast.querySelector('.toast-message');

    let iconClass, color;
    switch (type) {
        case 'success': iconClass = 'fas fa-check-circle'; color = 'var(--success-green)'; break;
        case 'error': iconClass = 'fas fa-exclamation-circle'; color = 'var(--error-red)'; break;
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


// --- FUNÇÕES DO FLUXO DE CHECKOUT ---

function openCheckoutModal(productId, imgSrc, nome, preco) {
    console.log("DEBUG: Abrindo modal para produto ID:", productId);
    resetCheckoutModal(); 

    const precoFloat = parseFloat(preco);
    
    checkoutProdutoDetalhes.innerHTML = `
        ${imgSrc ? `<img src="${imgSrc}" alt="${nome}" style="max-width: 80px; margin-bottom: 0.5rem; border-radius: 4px;">` : ''}
        <h3 style="margin: 0.5rem 0;">${nome || 'Produto Selecionado'}</h3>
        <p class="checkout-preco" style="font-size: 1.4rem; font-weight: bold; color: var(--orange-web);">R$ ${precoFloat.toFixed(2).replace('.', ',')}</p>
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
    
    if (!validateCheckoutForm()) {
        return;
    }

    const nomeCliente = checkoutNomeInput.value;
    const emailCliente = checkoutEmailInput.value;
    const productId = checkoutProductIdInput.value; 
    
    // NOVO: Captura o código do vendedor selecionado
    const vendedorCodigo = checkoutVendedorSelect.value;

    const dadosParaEnvio = {
        email: emailCliente,
        nome: nomeCliente,
        product_id: parseInt(productId),
        vendedor_codigo: vendedorCodigo // Envia o código (será "" se "Opcional" for selecionado)
    };
    console.log("DEBUG: Enviando para API:", dadosParaEnvio);

    showLoadingInCheckoutResult();
    checkoutForm.style.display = 'none'; 

    try {
        // A rota é relativa, pois o script.js está no mesmo domínio do app.py
        const response = await fetch('/api/cobrancas', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dadosParaEnvio),
        });

        const result = await response.json();
         console.log("DEBUG: Resposta da API:", result);

        if (response.ok) {
            showQrCodeInCheckoutResult(result);
            showToast('Cobrança PIX gerada! Pague para receber.', 'success');
        } else {
            throw new Error(result.message || 'Erro ao gerar cobrança PIX.');
        }

    } catch (error) {
        console.error('Erro no checkout:', error);
        showErrorInCheckoutResult(error.message);
        showToast(error.message, 'error');
        checkoutForm.style.display = 'block'; 
    }
}

function validateCheckoutForm() {
    clearFieldErrors(checkoutForm); 
    let isValid = true;

    const nome = checkoutNomeInput.value.trim();
    const email = checkoutEmailInput.value.trim();

    if (nome.length < 2) {
        showFieldError(checkoutNomeInput, 'Nome deve ter pelo menos 2 caracteres');
        isValid = false;
    }

    if (!email) {
        showFieldError(checkoutEmailInput, 'Email é obrigatório');
        isValid = false;
    } else if (!isValidEmail(email)) {
        showFieldError(checkoutEmailInput, 'Por favor, insira um email válido');
        isValid = false;
    }

    // O campo vendedor é opcional, não precisa de validação

    return isValid;
}

function showLoadingInCheckoutResult() {
    checkoutResultado.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div class="loading-spinner"></div>
            <p style="margin-top: 1rem;">Gerando sua cobrança PIX, aguarde...</p>
        </div>
    `;
}

function showQrCodeInCheckoutResult(data) {
    checkoutResultado.innerHTML = `
        <div style="text-align: center;">
            <h2 style="color: #27ae60; margin-bottom: 1rem;">
                <i class="fas fa-check-circle"></i>
                Pague com PIX para confirmar!
            </h2>
            <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                <img src="data:image/jpeg;base64,${data.qr_code_base64}" 
                     alt="PIX QR Code" 
                     style="max-width: 100%; max-height: 250px; border: 2px solid #e0e0e0; border-radius: 8px;">
            </div>
            <p style="margin: 1rem 0; font-weight: bold;">Ou copie e cole o código PIX:</p>
            <textarea readonly 
                      style="width: 100%; min-height: 100px; font-family: monospace; font-size: 0.9rem; padding: 0.5rem; border: 2px solid #e0e0e0; border-radius: 5px; background: #f8f9fa; resize: none; color: #333;"
                      onclick="this.select(); document.execCommand('copy'); showToast('Código PIX copiado!', 'success');">${data.qr_code_text}</textarea>
            <p style="margin-top: 1rem; color: #666; font-size: 0.9rem;">
                <i class="fas fa-info-circle"></i>
                Clique no código acima para copiá-lo
            </p>
            ${data.cobranca && data.cobranca.valor ? `<p style="margin-top: 1rem; font-size: 1.1rem; font-weight: bold; color: #27ae60;">Valor: R$ ${data.cobranca.valor.toFixed(2)}</p>` : ''}
           <p style="margin-top: 1.5rem; font-size: 0.9rem; color: #555;">Após o pagamento, você receberá o produto no seu email.</p>
        </div>
    `;
}

function showErrorInCheckoutResult(message) {
      checkoutResultado.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <h2 style="color: #e74c3c; margin-bottom: 1rem;">
                    <i class="fas fa-exclamation-triangle"></i>
                    Erro ao processar pagamento
                </h2>
                <p style="color: #e74c3c; font-weight: bold; margin-bottom: 1rem;">${message}</p>
                <p style="color: #666; font-size: 0.9rem;">
                    Por favor, verifique os dados e tente novamente. Se o problema persistir, entre em contato conosco.
                </p>
            </div>
        `;
}


// --- LÓGICA DO DOMContentLoaded (ATUALIZADA) ---

document.addEventListener('DOMContentLoaded', () => {
    
    // --- NOVO: Buscar e Preencher Vendedores ---
    async function carregarVendedores() {
        if (!checkoutVendedorSelect) return; // Sai se o dropdown não existir
        
        try {
            // Busca os vendedores da nova API (rota relativa)
            const response = await fetch('/api/vendedores');
            if (!response.ok) {
                throw new Error('Falha ao carregar lista de vendedores.');
            }
            const vendedores = await response.json();
            
            // Limpa opções antigas (exceto a primeira "Opcional")
            checkoutVendedorSelect.innerHTML = '<option value="">-- Vendedor --</option>';
            
            // Adiciona os vendedores ao dropdown
            vendedores.forEach(vendedor => {
                const option = document.createElement('option');
                option.value = vendedor.codigo_ranking; // Ex: 'NKD00101'
                option.textContent = vendedor.nome_vendedor; // Ex: 'Vendedor 1 - João'
                checkoutVendedorSelect.appendChild(option);
            });
            console.log("DEBUG: Dropdown de vendedores preenchido.");

        } catch (error) {
            console.error("DEBUG: Erro ao carregar vendedores:", error);
            // Mesmo se falhar, o checkout continua funcionando sem o vendedor
        }
    }
    
    // Carrega os vendedores assim que a página é carregada
    carregarVendedores();
    
    // --- FIM DO NOVO BLOCO ---


    // SELETORES GLOBAIS
    const comprarButtons = document.querySelectorAll('.comprar-btn');
    
    // 1. Ouvinte para os botões "Comprar Agora" na página principal
    comprarButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            const btn = event.target.closest('.comprar-btn');
            
            const productId = btn.dataset.productId;
            const card = btn.closest('.book-card');
            
            const imgSrc = card?.querySelector('img')?.src;
            const nome = card?.querySelector('h3')?.textContent;
            
            let preco = btn.dataset.productPrice;

            if (!preco) {
                const precoText = card?.querySelector('.book-price')?.textContent.replace('R$', '').replace(',', '.').trim();
                preco = precoText;
            }

            if (productId) {
                openCheckoutModal(productId, imgSrc, nome, preco);
            } else {
                console.error("DEBUG: Product ID não encontrado no botão.");
            }
        });
    });

    // 2. Ouvinte para fechar o Modal de Checkout
    if (checkoutModalClose) {
        checkoutModalClose.addEventListener('click', closeCheckoutModal);
    }
    window.addEventListener('click', (event) => {
        if (event.target == checkoutModal) {
            closeCheckoutModal();
        }
    });

    // 3. Ouvinte para o ENVIO do formulário DENTRO do Modal de Checkout
    if (checkoutForm) {
        checkoutForm.addEventListener('submit', handleCheckoutSubmit);
    } else {
        console.error("DEBUG: Formulário de checkout (#checkout-form) não encontrado!");
    }

    // Ouvinte para fechar o toast ao clicar nele
    if (feedbackToast) {
        feedbackToast.addEventListener('click', () => {
            feedbackToast.classList.remove('show');
            feedbackToast.style.display = 'none';
        });
    }
    
    console.log("DEBUG: Script carregado e ouvintes configurados.");
});

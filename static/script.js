document.addEventListener('DOMContentLoaded', () => {
    
    // --- SELETORES GLOBAIS (APENAS PARA O NOVO MODAL) ---
    const checkoutModal = document.getElementById('checkout-modal');
    const checkoutModalClose = document.getElementById('checkout-modal-close');
    const checkoutProdutoDetalhes = document.getElementById('checkout-produto-detalhes');
    const checkoutForm = document.getElementById('checkout-form');
    const checkoutResultado = document.getElementById('checkout-resultado');
    const checkoutProductIdInput = document.getElementById('checkout_product_id');
    const checkoutNomeInput = document.getElementById('checkout_nome');
    const checkoutEmailInput = document.getElementById('checkout_email');
    
    // Usa o novo ID para o toast, se você o renomeou no HTML
    const feedbackToast = document.getElementById('feedback-toast'); 
    
    // --- EVENT LISTENERS ---

    // 1. Ouvinte para os botões "Comprar Agora" na página principal
    const comprarButtons = document.querySelectorAll('.comprar-btn');
    console.log("DEBUG: Botões encontrados:", comprarButtons); // DEBUG
    comprarButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            console.log("DEBUG: Botão Comprar clicado!"); // DEBUG
            const productId = event.target.closest('.comprar-btn').dataset.productId;
            
            const card = event.target.closest('.book-card'); // Corrigido para .book-card
            const imgSrc = card?.querySelector('img')?.src;
            const nome = card?.querySelector('h3')?.textContent;
            const preco = card?.querySelector('.book-price')?.textContent; // Corrigido para .book-price

            if (productId) { // Só abre se tiver ID
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
        console.error("DEBUG: Formulário de checkout (#checkout-form) não encontrado!"); // DEBUG
    }

    // --- FUNÇÕES DO FLUXO DE CHECKOUT ---

    function openCheckoutModal(productId, imgSrc, nome, preco) {
        console.log("DEBUG: Abrindo modal para produto ID:", productId); // DEBUG
        resetCheckoutModal(); 
        checkoutProdutoDetalhes.innerHTML = `
            ${imgSrc ? `<img src="${imgSrc}" alt="${nome}" style="max-width: 80px; margin-bottom: 0.5rem; border-radius: 4px;">` : ''}
            <h3 style="margin: 0.5rem 0;">${nome || 'Produto Selecionado'}</h3>            
            <p class="checkout-preco">${preco || ''}</p> 
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

        const dadosParaEnvio = {
            email: emailCliente,
            nome: nomeCliente,
            product_id: parseInt(productId) 
        };
        console.log("DEBUG: Enviando para API:", dadosParaEnvio); // DEBUG

        showLoadingInCheckoutResult();
        checkoutForm.style.display = 'none'; 

        try {
            const response = await fetch('/api/cobrancas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(dadosParaEnvio),
            });

            const result = await response.json();
             console.log("DEBUG: Resposta da API:", result); // DEBUG

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

        return isValid;
    }


    // --- FUNÇÕES AUXILIARES DE UI (MODAL E TOAST) ---
    
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
                          style="width: 100%; min-height: 100px; font-family: monospace; font-size: 0.9rem; padding: 0.5rem; border: 2px solid #e0e0e0; border-radius: 5px; background: #f8f9fa; resize: none; color: #333;;"
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
    
    // Funções de validação e UI 
    
    function isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

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
        const inputs = form.querySelectorAll('input, textarea');
        inputs.forEach(input => {
            input.style.borderColor = '#ccc'; 
        });
    }

    function showToast(message, type = 'info') {
        // Usa a variável feedbackToast definida no início
        if (!feedbackToast) {
            console.warn("Elemento Toast não encontrado com ID: feedback-toast"); // DEBUG
            return; 
        }

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

    // Fecha o toast ao clicar nele
    if (feedbackToast) {
        feedbackToast.addEventListener('click', () => {
            feedbackToast.classList.remove('show');
            feedbackToast.style.display = 'none';
        });
    }

    // Validação em tempo real para o modal
    const modalInputs = checkoutForm ? checkoutForm.querySelectorAll('input[required]') : [];
    modalInputs.forEach(input => {
        input.addEventListener('blur', () => { 
            if (input.value.trim() === '') {
                input.style.borderColor = '#e74c3c'; 
            } else {
                if (input.id === 'checkout_email' && !isValidEmail(input.value)) {
                    input.style.borderColor = '#e74c3c';
                } else {
                    input.style.borderColor = '#ccc'; 
                }
            }
        });
        input.addEventListener('focus', () => { 
            input.style.borderColor = '#667eea'; 
        });
    });

    console.log("DEBUG: Script carregado e ouvintes configurados."); // DEBUG

}); // Fim do DOMContentLoaded

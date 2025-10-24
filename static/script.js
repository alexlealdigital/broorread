document.addEventListener('DOMContentLoaded', () => {
    // Seleciona o formulário de criação de cobrança
    const formCobranca = document.getElementById('form-cobranca');

    // Seleciona a área para mostrar o resultado (modal)
    const modal = document.getElementById('modal-detalhes');
    const modalBody = document.getElementById('modal-body');
    const modalClose = document.querySelector('.modal-close');

    // Elementos para feedback visual
    const toast = document.getElementById('toast');

    // Adiciona um "ouvinte" para o ENVIO do formulário
    formCobranca.addEventListener('submit', async (event) => {
        // Previne o comportamento padrão do formulário (que é recarregar a página)
        event.preventDefault();

        // Validação do formulário antes do envio
        if (!validateForm()) {
            return;
        }

        // Pega os dados do formulário
        const formData = new FormData(formCobranca);
        const dadosCobranca = Object.fromEntries(formData.entries());

        // --- [CORREÇÃO 1: OBJETO PARA PLANO A] ---
        // Agora enviamos product_id e removemos titulo/valor
        const dadosParaEnvio = {
            email: dadosCobranca.cliente_email,
            nome: dadosCobranca.cliente_nome,
            
            // Hardcoded para o seu produto de teste ID=1
            // Você pode tornar isso dinâmico se tiver vários botões de compra
            product_id: 1 
        };
        // --- FIM DA CORREÇÃO 1 ---

        // Mostra uma mensagem de "carregando"
        showLoadingInModal();

        try {
            // CHAMA A NOSSA API (MÉTODO POST)
            const response = await fetch('/api/cobrancas', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                // Envia os dados corrigidos para o backend
                body: JSON.stringify(dadosParaEnvio),
            });

            const result = await response.json();

            if (response.ok) {
                // SUCESSO! Mostra o QR Code no Modal
                showQrCodeInModal(result);
                showToast('Cobrança criada com sucesso! Pague o PIX para receber.', 'success');
                
                // Limpa o formulário após sucesso
                formCobranca.reset();
            } else {
                // Se a API retornar um erro
                throw new Error(result.message || 'Ocorreu um erro ao gerar a cobrança.');
            }

        } catch (error) {
            // Se houver um erro de rede ou na API
            console.error('Erro ao criar cobrança:', error);
            showErrorInModal(error.message);
            showToast(error.message, 'error');
        }
    });

    // --- [CORREÇÃO 2: VALIDAÇÃO PARA PLANO A] ---
    // Função para validar o formulário (sem titulo e valor)
    function validateForm() {
        const email = document.getElementById('cliente_email').value;
        const nome = document.getElementById('cliente_nome').value;
        // const titulo = document.getElementById('titulo').value; // REMOVIDO
        // const valor = document.getElementById('valor').value;   // REMOVIDO

        // Limpa mensagens de erro anteriores
        clearFieldErrors();

        let isValid = true;

        // Validação de email
        if (!email) {
            showFieldError('cliente_email', 'Email é obrigatório');
            isValid = false;
        } else if (!isValidEmail(email)) {
            showFieldError('cliente_email', 'Por favor, insira um email válido');
            isValid = false;
        }

        // Validação de nome
        if (!nome || nome.trim().length < 2) {
            showFieldError('cliente_nome', 'Nome deve ter pelo menos 2 caracteres');
            isValid = false;
        }

        // Validações de 'titulo' e 'valor' REMOVIDAS

        return isValid;
    }
    // --- FIM DA CORREÇÃO 2 ---

    // Função para validar email
    function isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    // Função para mostrar erro em campo específico
    function showFieldError(fieldId, message) {
        const field = document.getElementById(fieldId);
        // Evita adicionar erro se o campo não existir mais no HTML
        if (!field) return; 

        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error';
        errorDiv.textContent = message;
        errorDiv.style.color = '#e74c3c';
        errorDiv.style.fontSize = '0.9rem';
        errorDiv.style.marginTop = '0.25rem';
        
        field.style.borderColor = '#e74c3c';
        // Insere o erro logo após o campo
        field.parentNode.insertBefore(errorDiv, field.nextSibling); 
    }

    // Função para limpar erros de campo
    function clearFieldErrors() {
        const errorDivs = document.querySelectorAll('.field-error');
        errorDivs.forEach(div => div.remove());
        
        const inputs = document.querySelectorAll('input, textarea');
        inputs.forEach(input => {
            input.style.borderColor = '#e0e0e0'; // Cor padrão da borda
        });
    }

    // Funções auxiliares para controlar o Modal (sem mudanças)
    function showLoadingInModal() {
        modalBody.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <div class="loading-spinner"></div>
                <p style="margin-top: 1rem;">Gerando sua cobrança, aguarde...</p>
            </div>
        `;
        modal.style.display = 'block';
    }

    function showQrCodeInModal(data) {
        modalBody.innerHTML = `
            <div style="text-align: center;">
                <h2 style="color: #27ae60; margin-bottom: 1rem;">
                    <i class="fas fa-check-circle"></i>
                    Pague com PIX para confirmar!
                </h2>
                <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                    <img src="data:image/jpeg;base64,${data.qr_code_base64}" 
                         alt="PIX QR Code" 
                         style="max-width: 100%; border: 2px solid #e0e0e0; border-radius: 8px;">
                </div>
                <p style="margin: 1rem 0; font-weight: bold;">Ou copie e cole o código PIX:</p>
                <textarea readonly 
                          style="width: 100%; min-height: 100px; font-family: monospace; font-size: 0.9rem; padding: 0.5rem; border: 2px solid #e0e0e0; border-radius: 5px; background: #f8f9fa;"
                          onclick="this.select()">${data.qr_code_text}</textarea>
                <p style="margin-top: 1rem; color: #666; font-size: 0.9rem;">
                    <i class="fas fa-info-circle"></i>
                    Clique no código acima para selecioná-lo e copiá-lo
                </p>
                ${data.cobranca && data.cobranca.valor ? `<p style="margin-top: 1rem; font-size: 1.1rem; font-weight: bold; color: #27ae60;">Valor: R$ ${data.cobranca.valor.toFixed(2)}</p>` : ''}
            </div>
        `;
         modal.style.display = 'block'; // Garante que o modal apareça
    }

    function showErrorInModal(message) {
        modalBody.innerHTML = `
            <div style="text-align: center; padding: 2rem;">
                <h2 style="color: #e74c3c; margin-bottom: 1rem;">
                    <i class="fas fa-exclamation-triangle"></i>
                    Erro ao processar pagamento
                </h2>
                <p style="color: #e74c3c; font-weight: bold; margin-bottom: 1rem;">${message}</p>
                <p style="color: #666; font-size: 0.9rem;">
                    Por favor, verifique os dados e tente novamente. Se o problema persistir, entre em contato conosco.
                </p>
                <button onclick="document.getElementById('modal-detalhes').style.display='none'" 
                        style="margin-top: 1rem; padding: 0.5rem 1rem; background: #e74c3c; color: white; border: none; border-radius: 5px; cursor: pointer;">
                    Fechar
                </button>
            </div>
        `;
        modal.style.display = 'block';
    }

    // Função para mostrar toast notifications (sem mudanças)
    function showToast(message, type = 'info') {
        const toastContent = toast.querySelector('.toast-content');
        const toastIcon = toast.querySelector('.toast-icon');
        const toastMessage = toast.querySelector('.toast-message');

        let icon, color;
        switch (type) {
            case 'success':
                icon = 'fas fa-check-circle';
                color = '#27ae60';
                break;
            case 'error':
                icon = 'fas fa-exclamation-circle';
                color = '#e74c3c';
                break;
            default:
                icon = 'fas fa-info-circle';
                color = '#3498db';
        }

        toastIcon.className = icon;
        toastMessage.textContent = message;
        toast.style.background = color;
        toast.style.display = 'block';

        setTimeout(() => {
            toast.style.display = 'none';
        }, 5000);
    }

    // Fecha o modal ao clicar no 'X' (sem mudanças)
    if (modalClose) {
        modalClose.addEventListener('click', () => {
            modal.style.display = 'none';
        });
    }

    // Fecha o modal ao clicar fora dele (sem mudanças)
    window.addEventListener('click', (event) => {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    });

    // Fecha o toast ao clicar nele (sem mudanças)
    if (toast) {
        toast.addEventListener('click', () => {
            toast.style.display = 'none';
        });
    }

    // Lógica para trocar de abas (sem mudanças)
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    navButtons.forEach(button => {
        button.addEventListener('click', () => {
            navButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(tab => tab.classList.remove('active'));

            button.classList.add('active');
            const targetTab = document.getElementById(`tab-${button.dataset.tab}`);
            if (targetTab) {
                targetTab.classList.add('active');
            }
        });
    });

    // Máscara para telefone (sem mudanças)
    const telefoneInput = document.getElementById('cliente_telefone');
    if (telefoneInput) {
        telefoneInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/\D/g, '');
            // Limita a 11 dígitos
            value = value.substring(0, 11); 
            if (value.length > 10) { // Celular (XX) XXXXX-XXXX
                value = value.replace(/^(\d{2})(\d{5})(\d{4}).*/, '($1) $2-$3');
            } else if (value.length > 6) { // Fixo (XX) XXXX-XXXX
                value = value.replace(/^(\d{2})(\d{4})(\d{0,4}).*/, '($1) $2-$3');
            } else if (value.length > 2) { // (XX) XXXX
                value = value.replace(/^(\d{2})(\d{0,4}).*/, '($1) $2');
            } else if (value.length > 0) { // (XX
                value = value.replace(/^(\d*)/, '($1');
            }
            e.target.value = value;
        });
    }

    // Máscara para CPF/CNPJ (sem mudanças)
    const documentoInput = document.getElementById('cliente_documento');
    if (documentoInput) {
        documentoInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/\D/g, '');
             // Limita a 14 dígitos (CNPJ)
            value = value.substring(0, 14);
            if (value.length <= 11) { // CPF
                value = value.replace(/(\d{3})(\d)/, '$1.$2');
                value = value.replace(/(\d{3})(\d)/, '$1.$2');
                value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
            } else { // CNPJ
                value = value.replace(/^(\d{2})(\d)/, '$1.$2');
                value = value.replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3');
                value = value.replace(/\.(\d{3})(\d)/, '.$1/$2');
                value = value.replace(/(\d{4})(\d)/, '$1-$2');
            }
            e.target.value = value;
        });
    }

    // Validação em tempo real (sem mudanças)
    // Seleciona apenas os campos que ainda existem e são obrigatórios
    const requiredInputs = document.querySelectorAll('#cliente_email, #cliente_nome'); 
    requiredInputs.forEach(input => {
        input.addEventListener('blur', () => { // Ao perder o foco
            if (input.value.trim() === '') {
                input.style.borderColor = '#e74c3c'; // Borda vermelha se vazio
            } else {
                 // Verifica se é email e se é válido
                if (input.id === 'cliente_email' && !isValidEmail(input.value)) {
                    input.style.borderColor = '#e74c3c'; 
                } else {
                    input.style.borderColor = '#27ae60'; // Borda verde se preenchido e válido
                }
            }
        });

        input.addEventListener('focus', () => { // Ao ganhar o foco
            input.style.borderColor = '#667eea'; // Borda azul
        });
    });
});

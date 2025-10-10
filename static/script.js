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

        // CORREÇÃO: Mapeia o campo cliente_email para email que o backend espera
        const dadosParaEnvio = {
            email: dadosCobranca.cliente_email,
            nome: dadosCobranca.cliente_nome,
            telefone: dadosCobranca.cliente_telefone,
            documento: dadosCobranca.cliente_documento,
            titulo: dadosCobranca.titulo,
            descricao: dadosCobranca.descricao,
            valor: parseFloat(dadosCobranca.valor)
        };

        // Mostra uma mensagem de "carregando"
        showLoadingInModal();

        try {
            // CHAMA A NOSSA API (MÉTODO POST)
            const response = await fetch('/api/cobrancas', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                // Envia os dados mapeados para o backend
                body: JSON.stringify(dadosParaEnvio),
            });

            const result = await response.json();

            if (response.ok) {
                // SUCESSO! Mostra o QR Code no Modal
                showQrCodeInModal(result);
                showToast('Cobrança criada com sucesso!', 'success');
                
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

    // Função para validar o formulário
    function validateForm() {
        const email = document.getElementById('cliente_email').value;
        const nome = document.getElementById('cliente_nome').value;
        const titulo = document.getElementById('titulo').value;
        const valor = document.getElementById('valor').value;

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

        // Validação de título
        if (!titulo || titulo.trim().length < 3) {
            showFieldError('titulo', 'Título deve ter pelo menos 3 caracteres');
            isValid = false;
        }

        // Validação de valor
        if (!valor || parseFloat(valor) <= 0) {
            showFieldError('valor', 'Valor deve ser maior que zero');
            isValid = false;
        }

        return isValid;
    }

    // Função para validar email
    function isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    // Função para mostrar erro em campo específico
    function showFieldError(fieldId, message) {
        const field = document.getElementById(fieldId);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error';
        errorDiv.textContent = message;
        errorDiv.style.color = '#e74c3c';
        errorDiv.style.fontSize = '0.9rem';
        errorDiv.style.marginTop = '0.25rem';
        
        field.style.borderColor = '#e74c3c';
        field.parentNode.appendChild(errorDiv);
    }

    // Função para limpar erros de campo
    function clearFieldErrors() {
        const errorDivs = document.querySelectorAll('.field-error');
        errorDivs.forEach(div => div.remove());
        
        const inputs = document.querySelectorAll('input, textarea');
        inputs.forEach(input => {
            input.style.borderColor = '#e0e0e0';
        });
    }

    // Funções auxiliares para controlar o Modal
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
                ${data.valor ? `<p style="margin-top: 1rem; font-size: 1.1rem; font-weight: bold; color: #27ae60;">Valor: R$ ${data.valor.toFixed(2)}</p>` : ''}
            </div>
        `;
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

    // Função para mostrar toast notifications
    function showToast(message, type = 'info') {
        const toastContent = toast.querySelector('.toast-content');
        const toastIcon = toast.querySelector('.toast-icon');
        const toastMessage = toast.querySelector('.toast-message');

        // Define ícone e cor baseado no tipo
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

        // Auto-hide após 5 segundos
        setTimeout(() => {
            toast.style.display = 'none';
        }, 5000);
    }

    // Fecha o modal ao clicar no 'X'
    modalClose.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    // Fecha o modal ao clicar fora dele
    window.addEventListener('click', (event) => {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    });

    // Fecha o toast ao clicar nele
    toast.addEventListener('click', () => {
        toast.style.display = 'none';
    });

    // Lógica para trocar de abas
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    navButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove a classe 'active' de todos
            navButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(tab => tab.classList.remove('active'));

            // Adiciona 'active' ao botão e tab clicados
            button.classList.add('active');
            document.getElementById(`tab-${button.dataset.tab}`).classList.add('active');
        });
    });

    // Máscara para telefone
    const telefoneInput = document.getElementById('cliente_telefone');
    if (telefoneInput) {
        telefoneInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length <= 11) {
                value = value.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
                if (value.length < 14) {
                    value = value.replace(/(\d{2})(\d{4})(\d{4})/, '($1) $2-$3');
                }
            }
            e.target.value = value;
        });
    }

    // Máscara para CPF
    const documentoInput = document.getElementById('cliente_documento');
    if (documentoInput) {
        documentoInput.addEventListener('input', (e) => {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length <= 11) {
                value = value.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
            } else {
                value = value.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
            }
            e.target.value = value;
        });
    }

    // Validação em tempo real
    const inputs = document.querySelectorAll('input[required], textarea[required]');
    inputs.forEach(input => {
        input.addEventListener('blur', () => {
            if (input.value.trim() === '') {
                input.style.borderColor = '#e74c3c';
            } else {
                input.style.borderColor = '#27ae60';
            }
        });

        input.addEventListener('focus', () => {
            input.style.borderColor = '#667eea';
        });
    });
});

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Teste de Validação de Licença</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #0d1117;
            color: #c9d1d9;
        }
        .container {
            max-width: 600px;
        }
        /* Estilo para a caixa de resultado JSON */
        #result-area {
            white-space: pre-wrap;
            background-color: #161b22;
            border: 1px solid #30363d;
            max-height: 400px;
            overflow-y: auto;
        }
    </style>
</head>
<body class="p-4">

    <div class="container mx-auto mt-10 p-6 bg-gray-800 rounded-xl shadow-2xl">
        <h1 class="text-3xl font-bold text-green-400 mb-6 text-center">API de Validação de Chave</h1>
        <p class="text-gray-400 mb-6 text-center">Teste a rota <code>/api/validar_chave</code> do seu servidor Flask (Render). Você está testando a ativação de um App.</p>

        <form id="validation-form" class="space-y-4">
            
            <div class="p-4 bg-gray-700 rounded-lg">
                <label for="server-url" class="block text-sm font-medium text-gray-300">URL Base do Servidor (Render)</label>
                <input type="url" id="server-url" value="https://mercadopago-final.onrender.com"
                       class="mt-1 block w-full p-3 border border-gray-600 rounded-lg bg-gray-900 text-white focus:ring-blue-500 focus:border-blue-500" required>
            </div>

            <div class="space-y-4 p-4 border border-blue-600 rounded-xl bg-blue-900/20">
                <h2 class="text-xl font-semibold text-blue-300">Dados da Chave</h2>
                
                <div>
                    <label for="chave-serial" class="block text-sm font-medium text-gray-300">Chave Serial (APP1-0004-TEST-ADFG)</label>
                    <input type="text" id="chave-serial" value="APP1-0004-TEST-ADFG"
                           class="mt-1 block w-full p-3 border border-gray-600 rounded-lg bg-gray-900 text-yellow-400 font-mono" required>
                </div>

                <div>
                    <label for="product-id" class="block text-sm font-medium text-gray-300">ID do Produto (3 - App1)</label>
                    <input type="number" id="product-id" value="3"
                           class="mt-1 block w-full p-3 border border-gray-600 rounded-lg bg-gray-900 text-white" required>
                </div>
            </div>

            <button type="submit" id="submit-btn"
                    class="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-3 px-4 rounded-xl transition duration-200 flex items-center justify-center space-x-2">
                <i class="fas fa-check-circle"></i> <span>Validar e Ativar Chave</span>
            </button>
        </form>

        <div class="mt-8">
            <h2 class="text-xl font-semibold text-gray-300 mb-3">Resposta da API</h2>
            <pre id="result-area" class="p-4 text-sm rounded-lg"></pre>
        </div>
    </div>

    <!-- Font Awesome Icons -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/js/all.min.js" xintegrity="sha512-..." crossorigin="anonymous"></script>

    <script>
        document.getElementById('validation-form').addEventListener('submit', async (e) => {
            e.preventDefault();

            const serverUrl = document.getElementById('server-url').value.trim().replace(/\/$/, '');
            const chaveSerial = document.getElementById('chave-serial').value.trim().toUpperCase();
            const productId = document.getElementById('product-id').value.trim();
            const resultArea = document.getElementById('result-area');
            const submitBtn = document.getElementById('submit-btn');

            // Ajuste para garantir que a rota seja enviada corretamente
            const apiUrl = `${serverUrl}/api/validar_chave`;
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Validando...';
            resultArea.textContent = 'Aguardando resposta...';
            resultArea.classList.remove('text-red-400', 'text-green-400');
            resultArea.classList.add('text-yellow-400');

            const payload = {
                chave_serial: chaveSerial,
                product_id: productId
            };

            try {
                const response = await fetch(apiUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(payload),
                });

                const data = await response.json();
                
                resultArea.textContent = JSON.stringify(data, null, 2);

                if (response.ok && data.status === 'valid') {
                    resultArea.classList.remove('text-yellow-400');
                    resultArea.classList.add('text-green-400');
                    alert(`SUCESSO! Chave ativada: ${chaveSerial}`);
                } else if (data.status === 'invalid' || data.status === 'error') {
                    resultArea.classList.remove('text-yellow-400');
                    resultArea.classList.add('text-red-400');
                    alert(`FALHA na validação: ${data.message}`);
                } else {
                    resultArea.classList.remove('text-yellow-400');
                    resultArea.classList.add('text-red-400');
                }
                
            } catch (error) {
                resultArea.textContent = `Erro de Conexão: ${error.message}. Verifique a URL do servidor ou se o App está rodando.`;
                resultArea.classList.remove('text-yellow-400');
                resultArea.classList.add('text-red-400');
                alert("Erro de conexão com a API.");
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-check-circle"></i> <span>Validar e Ativar Chave</span>';
            }
        });
    </script>
</body>
</html>

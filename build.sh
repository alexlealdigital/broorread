#!/usr/bin/env bash
set -e
 
echo "==> Instalando Ghostscript..."
apt-get install -y ghostscript
 
echo "==> Instalando dependências Python..."
pip install -r requirements.txt
 
echo "==> Build concluído."

import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')
TOKENS_VALIDOS = {}

# =========================================================
# CONEXÃO POSTGRES
# =========================================================
def obter_conexao():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode='require'
    )

# =========================================================
# CRIAR TABELAS (ATUALIZADO COM OS NOVOS CAMPOS FINANCEIROS)
# =========================================================
def criar_tabelas():
    comandos = (
        """
        CREATE TABLE IF NOT EXISTS usuarios_corretores (
            id UUID PRIMARY KEY,
            nome_completo VARCHAR(255) NOT NULL,
            cpf_cnpj VARCHAR(14) UNIQUE NOT NULL,
            status VARCHAR(50) DEFAULT 'ativo'
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS propostas_credito (
            id UUID PRIMARY KEY,
            nome_cliente VARCHAR(255),
            whatsapp_cliente VARCHAR(50),
            comprador_doc VARCHAR(50),
            vendedor_doc VARCHAR(50),
            data_nascimento VARCHAR(20),
            vertical_produto VARCHAR(50) NOT NULL,
            sub_produto VARCHAR(100),
            valor_total DECIMAL(15,2) NOT NULL,
            renda_comprovada DECIMAL(15,2) NOT NULL,
            prazo_meses INT NOT NULL,
            banco_escolhido VARCHAR(100),
            placa_veiculo VARCHAR(10),
            renavam_veiculo VARCHAR(20),
            valor_entrada DECIMAL(15,2) DEFAULT 0.00,
            status_esteira VARCHAR(50) DEFAULT 'simulacao',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn = None
    try:
        conn = obter_conexao()
        cur = conn.cursor()
        for comando in comandos:
            cur.execute(comando)
        conn.commit()
        cur.close()
        print("Tabelas estruturadas com sucesso.")
    except Exception as erro:
        print("Erro ao criar tabelas de dados:", erro)
    finally:
        if conn:
            conn.close()

# =========================================================
# HOME
# =========================================================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "sistema": "NEXUS Core API"
    })
# =========================================================
# CALCULAR CRÉDITO (MOTOR ATUALIZADO PARA DÉBITOS E SCORE)
# =========================================================
@app.route('/calcular_credito', methods=['POST'])
def calcular_credito():
    dados = request.get_json() or {}
    try:
        # 1. Coleta estruturada dos novos campos cadastrais e operacionais
        vertical = dados.get('vertical', 'imovel')
        nome_cliente = dados.get('nome_cliente', '').upper()
        whatsapp = dados.get('whatsapp', '')
        comprador = dados.get('comprador', '')
        vendedor = dados.get('vendedor', '')
        data_nascimento = dados.get('data_nascimento', '')
        
        valor = float(dados.get('valor', 0))
        renda = float(dados.get('renda', 0))
        prazo = int(dados.get('prazo', 1))
        banco = dados.get('banco', 'Desconhecido')
        
        # Inputs específicos de veículos, subprodutos e regularizações
        sub_produto = dados.get('sub_produto', '')
        placa = dados.get('placa', '').upper()
        renavam = dados.get('renavam', '')
        entrada = float(dados.get('entrada', 0))
        forma_pagamento = dados.get('forma_pagamento', 'cartao')

        # 2. Matriz de Taxas e Tratamento de Regras do MVP Híbrido de Multas
        taxas = {
            'imovel': 0.095,   # 9.5% a.a.
            'veiculo': 0.145,  # 14.5% a.a.
            'agro': 0.085,     # 8.5% a.a.
            'global': 0.055,   # 5.5% a.a.
            'multas': 0.000,   # Taxa padrão base (Tratada na condicional abaixo)
            'score': 0.000
        }
        
        juros_anual = taxas.get(vertical, 0.095)
        
        # Definição e processamento de juros compostos baseados na vertical escolhida
        if vertical == 'global':
            juros_mensal = juros_anual / 12
        elif vertical == 'multas' and forma_pagamento == 'boleto':
            juros_mensal = 0.045  # Injeção da taxa parametrizada de 4.5% a.m. da mesa Nexus
            juros_anual = ((1 + juros_mensal) ** 12) - 1
        else:
            juros_mensal = ((1 + juros_anual) ** (1 / 12)) - 1

        # 3. Execução das fórmulas financeiras (Price vs SAC)
        valor_financiável = (valor - entrada) if vertical == 'multas' else valor
        
        if juros_mensal > 0 and prazo > 0:
            parcela_price = (valor_financiável * juros_mensal) / (1 - (1 + juros_mensal) ** (-prazo))
        else:
            parcela_price = valor_financiável / prazo if prazo > 0 else valor_financiável

        parcela_sac_inicial = (valor_financiável / prazo) + (valor_financiável * juros_mensal) if prazo > 0 else valor_financiável
        parcela_referencia = parcela_sac_inicial if vertical == 'imovel' else parcela_price

        # 4. Cálculo de Margem de Risco Comercial (Trava de 30%)
        comprometimento = (parcela_referencia / renda) * 100 if renda > 0 else 0
        
        if vertical == 'score' or vertical == 'multas':
            status_esteira = "aprovado" if (vertical == 'score' or (vertical == 'multas' and forma_pagamento == 'cartao') or (vertical == 'multas' and entrada >= (valor * 0.3))) else "recusado"
        else:
            status_esteira = "aprovado" if comprometimento <= 30 else "recusado"

        proposta_id = str(uuid.uuid4())

        # 5. Persistência e Gravação de dados no PostgreSQL (Insert Blindado)
        try:
            conn = obter_conexao()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO propostas_credito (
                    id, nome_cliente, whatsapp_cliente, comprador_doc, vendedor_doc, data_nascimento,
                    vertical_produto, sub_produto, valor_total, renda_comprovada, prazo_meses,
                    banco_escolhido, placa_veiculo, renavam_veiculo, valor_entrada, status_esteira
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                proposta_id, nome_cliente, whatsapp, comprador, vendedor, data_nascimento,
                vertical, sub_produto, valor, renda, prazo, banco, placa, renavam, entrada, status_esteira
            ))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as erro_db:
            print("Erro ao persistir simulação no Postgres:", erro_db)

        # 6. Payload JSON estruturado de retorno para renderização no front-end
        return jsonify({
            "sucesso": True,
            "proposta_id": proposta_id,
            "status": status_esteira,
            "comprometimento": round(comprometimento, 1),
            "taxa_anual": round(juros_anual * 100, 2),
            "taxa_mensal": round(juros_mensal * 100, 4),
            "parcela_price": round(parcela_price, 2),
            "parcela_sac": round(parcela_sac_inicial, 2),
            "parcela_referencia": round(parcela_referencia, 2)
        })
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500

# =========================================================
# START DA CONSOLIDAÇÃO DO SERVIDOR API
# =========================================================
if __name__ == '__main__':
    criar_tabelas()
    app.run(debug=True, host='0.0.0.0', port=5000)

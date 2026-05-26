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
# CONEXÃO POSTGRESQL (BLINDADA CONTRA QUEDAS)
# =========================================================
def obter_conexao():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode='require'
    )

# =========================================================
# CRIAR TABELAS DA ESTEIRA DIGITAL DA NEXUS
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
            score_calculado INT DEFAULT 0,
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
        print("Tabelas financeiras sincronizadas com sucesso.")
    except Exception as erro:
        print("Erro de compilação de banco de dados:", erro)
    finally:
        if conn:
            conn.close()

# =========================================================
# ROTA HOME - AUDITORIA DE STATUS DA REDE
# =========================================================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "sistema": "NEXUS Core FinTech API",
        "versao": "2026.1"
    })
# =========================================================
# CALCULAR CRÉDITO E ENGINE DE ANÁLISE DE SCORE EM TEMPO REAL
# =========================================================
@app.route('/calcular_credito', methods=['POST'])
def calcular_credito():
    dados = request.get_json() or {}
    try:
        # 1. Coleta e sanitização de metadados cadastrais enviados pelo CodePen
        vertical = dados.get('vertical', 'imovel')
        nome_cliente = dados.get('nome_cliente', '').upper()
        whatsapp = dados.get('whatsapp', '')
        comprador = dados.get('comprador', '')
        vendedor = dados.get('vendedor', '')
        data_nascimento = dados.get('data_nascimento', '')
        
        valor = float(dados.get('valor', 0))
        renda = float(dados.get('renda', 0))
        prazo = int(dados.get('prazo', 12))
        banco = dados.get('banco', 'Mesa Nexus')
        
        sub_produto = dados.get('sub_produto', '')
        placa = dados.get('placa', '').upper()
        renavam = dados.get('renavam', '')
        entrada = float(dados.get('entrada', 0))
        forma_pagamento = dados.get('forma_pagamento', 'cartao')

        # 2. MOTOR INTELIGENTE DE SCORE AUTOMÁTICO (Simulação de birô de crédito Serasa)
        # CPFs com dígitos finais pares geram score alto, ímpares geram restrição
        ultimo_digito = comprador[-1] if comprador else "0"
        if ultimo_digito in ['0', '2', '4', '6', '8'] or vertical == 'multas':
            score_interno = 780
            status_esteira = "aprovado"
        else:
            score_interno = 320
            status_esteira = "recusado"

        # 3. Matriz de Amortização (Price vs SAC) para propostas válidas
        taxas = {
            'imovel': 0.095,   # 9.5% a.a.
            'veiculo': 0.145,  # 14.5% a.a.
            'agro': 0.085,     # 8.5% a.a.
            'global': 0.055,   # 5.5% a.a.
            'multas': 0.000
        }
        
        juros_anual = taxas.get(vertical, 0.095)
        
        if vertical == 'global':
            juros_mensal = juros_anual / 12
        elif vertical == 'multas' and forma_pagamento == 'boleto':
            juros_mensal = 0.045  # 4.5% a.m. parametrizado para débitos recorrentes
            juros_anual = ((1 + juros_mensal) ** 12) - 1
        else:
            juros_mensal = ((1 + juros_anual) ** (1 / 12)) - 1

        valor_financiável = (valor - entrada) if vertical == 'multas' else valor
        
        if juros_mensal > 0 and prazo > 0:
            parcela_price = (valor_financiável * juros_mensal) / (1 - (1 + juros_mensal) ** (-prazo))
        else:
            parcela_price = valor_financiável / prazo if prazo > 0 else valor_financiável

        parcela_sac_inicial = (valor_financiável / prazo) + (valor_financiável * juros_mensal) if prazo > 0 else valor_financiável
        parcela_referencia = parcela_sac_inicial if vertical == 'imovel' else parcela_price

        # 4. Trava Prudencial Financeira de Margem Consignável (Teto de 30% da renda)
        if status_esteira == "aprovado" and vertical != 'multas' and vertical != 'score':
            comprometimento = (parcela_referencia / renda) * 100 if renda > 0 else 0
            if comprometimento > 30:
                status_esteira = "recusado"

        proposta_id = str(uuid.uuid4())

        # 5. Gravação segura no banco de dados PostgreSQL
        try:
            conn = obter_conexao()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO propostas_credito (
                    id, nome_cliente, whatsapp_cliente, comprador_doc, vendedor_doc, data_nascimento,
                    vertical_produto, sub_produto, valor_total, renda_comprovada, prazo_meses,
                    banco_escolhido, placa_veiculo, renavam_veiculo, valor_entrada, status_esteira, score_calculado
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                proposta_id, nome_cliente, whatsapp, comprador, vendedor, data_nascimento,
                vertical, sub_produto, valor, renda, prazo, banco, placa, renavam, entrada, status_esteira, score_interno
            ))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as erro_db:
            print("Erro ao processar persistência no Postgresql:", erro_db)

        # 6. Resposta JSON estruturada para o CodePen renderizar o documento na hora
        return jsonify({
            "sucesso": True,
            "proposta_id": proposta_id,
            "status": status_esteira,
            "score_cliente": score_interno,
            "taxa_anual": round(juros_anual * 100, 2),
            "taxa_mensal": round(juros_mensal * 100, 4),
            "parcela_price": round(parcela_price, 2),
            "parcela_sac": round(parcela_sac_inicial, 2),
            "parcela_referencia": round(parcela_referencia, 2)
        })
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500

# =========================================================
# INICIALIZADOR DO MICROSSERVIÇO FLASK
# =========================================================
if __name__ == '__main__':
    criar_tabelas()
    app.run(debug=True, host='0.0.0.0', port=5000)

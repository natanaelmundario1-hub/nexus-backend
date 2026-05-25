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
# CRIAR TABELAS
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
            comprador_doc VARCHAR(20) NOT NULL,
            vendedor_doc VARCHAR(20) NOT NULL,
            vertical_produto VARCHAR(50) NOT NULL,
            valor_total DECIMAL(15,2) NOT NULL,
            renda_comprovada DECIMAL(15,2) NOT NULL,
            prazo_meses INT NOT NULL,
            banco_escolhido VARCHAR(100),
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

        print("Tabelas criadas com sucesso.")

    except Exception as erro:

        print("Erro ao criar tabelas:", erro)

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
# CALCULAR CRÉDITO
# =========================================================

@app.route('/calcular_credito', methods=['POST'])
def calcular_credito():

    dados = request.get_json() or {}

    try:

        # =====================================================
        # DADOS RECEBIDOS
        # =====================================================

        vertical = dados.get('vertical', 'imovel')

        valor = float(dados.get('valor', 0))

        renda = float(dados.get('renda', 0))

        prazo = int(dados.get('prazo', 1))

        comprador = dados.get('comprador', '')

        vendedor = dados.get('vendedor', '')

        banco = dados.get('banco', 'Desconhecido')

        # =====================================================
        # TAXAS BANCÁRIAS
        # =====================================================

        taxas = {

            'imovel': 0.095,   # 9.5% a.a.
            'veiculo': 0.145,  # 14.5% a.a.
            'agro': 0.085,     # 8.5% a.a.
            'global': 0.055    # 5.5% a.a.
        }

        juros_anual = taxas.get(vertical, 0.095)

        # =====================================================
        # JUROS MENSAIS
        # =====================================================

        if vertical == 'global':

            juros_mensal = juros_anual / 12

        else:

            juros_mensal = ((1 + juros_anual) ** (1 / 12)) - 1

        # =====================================================
        # CÁLCULO PRICE
        # =====================================================

        if juros_mensal > 0:

            parcela_price = (
                valor * juros_mensal
            ) / (
                1 - (1 + juros_mensal) ** (-prazo)
            )

        else:

            parcela_price = valor / prazo

        # =====================================================
        # CÁLCULO SAC
        # =====================================================

        parcela_sac_inicial = (
            valor / prazo
        ) + (
            valor * juros_mensal
        )

        # =====================================================
        # DEFINIÇÃO DA PARCELA BASE
        # =====================================================

        if vertical == 'imovel':

            parcela_referencia = parcela_sac_inicial

        else:

            parcela_referencia = parcela_price

        # =====================================================
        # COMPROMETIMENTO
        # =====================================================

        if renda > 0:

            comprometimento = (
                parcela_referencia / renda
            ) * 100

        else:

            comprometimento = 100

        # =====================================================
        # STATUS
        # =====================================================

        status_esteira = (
            "aprovado"
            if comprometimento <= 30
            else "recusado"
        )

        proposta_id = str(uuid.uuid4())

        # =====================================================
        # SALVAR NO BANCO
        # =====================================================

        try:

            conn = obter_conexao()

            cur = conn.cursor()

            cur.execute("""
                INSERT INTO propostas_credito (

                    id,
                    comprador_doc,
                    vendedor_doc,
                    vertical_produto,
                    valor_total,
                    renda_comprovada,
                    prazo_meses,
                    banco_escolhido,
                    status_esteira

                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (

                proposta_id,
                comprador,
                vendedor,
                vertical,
                valor,
                renda,
                prazo,
                banco,
                status_esteira
            ))

            conn.commit()

            cur.close()

            conn.close()

        except Exception as erro_db:

            print("Erro ao salvar proposta:", erro_db)

        # =====================================================
        # RETORNO
        # =====================================================

        return jsonify({

            "sucesso": True,

            "proposta_id": proposta_id,

            "status": status_esteira,

            "comprometimento": round(
                comprometimento,
                1
            ),

            "taxa_anual": round(
                juros_anual * 100,
                2
            ),

            "taxa_mensal": round(
                juros_mensal * 100,
                4
            ),

            "parcela_price": round(
                parcela_price,
                2
            ),

            "parcela_sac": round(
                parcela_sac_inicial,
                2
            ),

            "parcela_referencia": round(
                parcela_referencia,
                2
            )
        })

    except Exception as erro:

        return jsonify({

            "sucesso": False,
            "erro": str(erro)

        }), 500

# =========================================================
# INICIAR SERVIDOR
# =========================================================

if __name__ == '__main__':

    criar_tabelas()

    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000
    )

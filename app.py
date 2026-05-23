import os
import uuid
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

TOKENS_VALIDOS = {}

# =========================================
# CONEXÃO COM BANCO
# =========================================

def obter_conexao():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# =========================================
# LOGIN
# =========================================

@app.route('/api/login', methods=['POST'])
def login():

    dados = request.get_json() or {}

    usuario = dados.get('usuario')
    senha = dados.get('senha')

    try:
        conn = obter_conexao()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            "SELECT * FROM usuarios WHERE senha = %s",
            (usuario,)
        )

        usuario_encontrado = cursor.fetchone()

        if usuario_encontrado:

            token = str(uuid.uuid4())

            TOKENS_VALIDOS[token] = usuario

            cursor.execute(
                "UPDATE usuarios SET token_ativo = %s WHERE senha = %s",
                (token, usuario)
            )

            conn.commit()

            cursor.close()
            conn.close()

            return jsonify({
                "sucesso": True,
                "token": token,
                "nome": usuario_encontrado['nome'],
                "creditos": usuario_encontrado.get('creditos', 0)
            })

        else:

            cursor.close()
            conn.close()

            return jsonify({
                "sucesso": False,
                "erro": "Usuário não encontrado."
            }), 401

    except Exception as e:

        return jsonify({
            "sucesso": False,
            "erro": str(e)
        }), 500

# =========================================
# CALCULAR CRÉDITO
# =========================================

@app.route('/api/calcular-credito', methods=['POST'])
def calcular_credito():

    dados = request.get_json() or {}

    token = dados.get('token')

    usuario_valido = None

    # Validação de token
    if token in TOKENS_VALIDOS:
        usuario_valido = TOKENS_VALIDOS[token]

    else:
        try:
            conn = obter_conexao()

            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                "SELECT senha, creditos FROM usuarios WHERE token_ativo = %s",
                (token,)
            )

            usuario_db = cursor.fetchone()

            if usuario_db:

                usuario_valido = usuario_db['senha']

                TOKENS_VALIDOS[token] = usuario_valido

                if usuario_db['creditos'] <= 0:

                    cursor.close()
                    conn.close()

                    return jsonify({
                        "erro": "Créditos esgotados."
                    }), 403

            cursor.close()
            conn.close()

        except:
            pass

    if not usuario_valido:
        return jsonify({
            "erro": "Sessão inválida."
        }), 401

    # =========================================
    # DESCONTAR 1 CRÉDITO
    # =========================================

    try:

        conn = obter_conexao()

        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE usuarios
            SET creditos = GREATEST(0, creditos - 1)
            WHERE senha = %s
            """,
            (usuario_valido,)
        )

        conn.commit()

        cursor.close()
        conn.close()

    except Exception as e:

        return jsonify({
            "erro": f"Erro ao descontar créditos: {str(e)}"
        }), 500

    # =========================================
    # DADOS DO CÁLCULO
    # =========================================

    valor_imovel = float(dados.get('valorImovel', 0))
    renda_bruta = float(dados.get('rendaBruta', 0))
    renda_informal = float(dados.get('rendaInformal', 0))
    entrada = float(dados.get('valorEntrada', 0))
    fgts = float(dados.get('valorFgts', 0))
    prazo_meses = int(dados.get('prazoMeses', 360))
    taxa_juros = float(dados.get('taxaJuros', 9.5))

    renda_total = renda_bruta + renda_informal

    valor_financiar = valor_imovel - entrada - fgts

    if valor_financiar <= 0:
        return jsonify({
            "mensagem": "Não há valor restante para financiar."
        })

    # =========================================
    # CÁLCULO SAC
    # =========================================

    taxa_mensal = (taxa_juros / 100) / 12

    amortizacao = valor_financiar / prazo_meses

    juros = valor_financiar * taxa_mensal

    primeira_parcela = amortizacao + juros

    comprometimento = renda_total * 0.30

    # =========================================
    # RESULTADO
    # =========================================

    if primeira_parcela <= comprometimento:

        mensagem = f"""
🛡️ CERTIFICADO DE VIABILIDADE APROVADO

Valor financiado: R$ {valor_financiar:,.2f}

Primeira parcela: R$ {primeira_parcela:,.2f}

Limite de renda (30%): R$ {comprometimento:,.2f}
"""

    else:

        mensagem = f"""
⚠️ CRÉDITO NÃO RECOMENDADO

Parcela estimada: R$ {primeira_parcela:,.2f}

Limite máximo de comprometimento: R$ {comprometimento:,.2f}
"""

    return jsonify({
        "mensagem": mensagem
    })

# =========================================
# FRONT-END
# =========================================

@app.route('/')
def home():
    return render_template('index.html')

# =========================================
# INICIAR SERVIDOR
# =========================================

if __name__ == '__main__':
    app.run(debug=True)

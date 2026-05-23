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

# ===================================
# CONEXÃO COM O BANCO
# ===================================

def obter_conexao():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# ===================================
# CRIAR TABELAS AUTOMATICAMENTE
# ===================================

def criar_tabelas():
    try:
        conn = obter_conexao()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255),
                nome VARCHAR(255),
                senha VARCHAR(255) UNIQUE,
                plano VARCHAR(100),
                corretores VARCHAR(50),
                creditos INTEGER DEFAULT 0,
                token_ativo TEXT
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicadores_mercado (
                chave VARCHAR(50) PRIMARY KEY,
                valor TEXT NOT NULL,
                fonte VARCHAR(100),
                ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print("Erro ao criar tabelas:", e)

# ===================================
# WEBHOOK MAKE / TALLY
# ===================================

@app.route('/api/webhook-registrar', methods=['POST'])
def webhook_registrar():

    dados = request.get_json() or {}

    email = dados.get('email', '')
    nome = dados.get('nome')
    senha = dados.get('senha')
    plano = dados.get('plano', 'Gratuito')
    corretores = dados.get('corretores', '1')

    if not nome or not senha:
        return jsonify({
            "sucesso": False,
            "erro": "Nome e WhatsApp obrigatórios."
        }), 400

    creditos_iniciais = 100 if corretores == 'mais de 3' else 20

    try:
        conn = obter_conexao()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            INSERT INTO usuarios
            (email, nome, senha, plano, corretores, creditos)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (senha)
            DO UPDATE SET
                plano = EXCLUDED.plano,
                corretores = EXCLUDED.corretores,
                creditos = usuarios.creditos + EXCLUDED.creditos
            RETURNING *;
        """, (
            email,
            nome,
            senha,
            plano,
            corretores,
            creditos_iniciais
        ))

        usuario = cursor.fetchone()

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "mensagem": "Usuário salvo com sucesso.",
            "usuario": usuario
        })

    except Exception as e:
        return jsonify({
            "sucesso": False,
            "erro": str(e)
        }), 500

# ===================================
# LOGIN
# ===================================

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
                "creditos": usuario_encontrado['creditos']
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

# ===================================
# ATUALIZAR CRÉDITOS
# ===================================

@app.route('/api/atualizar-creditos', methods=['POST'])
def atualizar_creditos():

    dados = request.get_json() or {}

    email = dados.get('email')
    quantidade = int(dados.get('creditos', 0))
    operacao = dados.get('operacao', 'adicionar')

    try:
        conn = obter_conexao()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        if operacao == 'remover':
            quantidade = -abs(quantidade)

        cursor.execute("""
            UPDATE usuarios
            SET creditos = GREATEST(0, creditos + %s)
            WHERE email = %s
            RETURNING creditos;
        """, (quantidade, email))

        resultado = cursor.fetchone()

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "novos_creditos": resultado['creditos']
        })

    except Exception as e:
        return jsonify({
            "sucesso": False,
            "erro": str(e)
        }), 500

# ===================================
# ATUALIZAR INDICADORES
# ===================================

@app.route('/api/atualizar-indicadores', methods=['POST'])
def atualizar_indicadores():

    dados = request.get_json() or {}

    chave = dados.get('chave')
    valor = dados.get('valor')
    fonte = dados.get('fonte')

    try:
        conn = obter_conexao()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO indicadores_mercado
            (chave, valor, fonte, ultima_atualizacao)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)

            ON CONFLICT (chave)
            DO UPDATE SET
                valor = EXCLUDED.valor,
                fonte = EXCLUDED.fonte,
                ultima_atualizacao = CURRENT_TIMESTAMP;
        """, (
            chave,
            str(valor),
            fonte
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "mensagem": "Indicador atualizado."
        })

    except Exception as e:
        return jsonify({
            "sucesso": False,
            "erro": str(e)
        }), 500

# ===================================
# OBTER INDICADORES
# ===================================

@app.route('/api/obter-indicadores', methods=['GET'])
def obter_indicadores():

    try:
        conn = obter_conexao()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT * FROM indicadores_mercado;")

        indicadores = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "indicadores": indicadores
        })

    except Exception as e:
        return jsonify({
            "sucesso": False,
            "erro": str(e)
        }), 500

# ===================================
# CALCULAR CRÉDITO
# ===================================

@app.route('/api/calcular-credito', methods=['POST'])
def calcular_credito():

    dados = request.get_json() or {}

    token = dados.get('token')

    usuario_valido = None

    if token in TOKENS_VALIDOS:
        usuario_valido = TOKENS_VALIDOS[token]

    else:
        try:
            conn = obter_conexao()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute("""
                SELECT senha, creditos
                FROM usuarios
                WHERE token_ativo = %s
            """, (token,))

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

        except Exception as e:
            return jsonify({
                "erro": str(e)
            }), 500

    if not usuario_valido:
        return jsonify({
            "erro": "Sessão inválida."
        }), 401

    # CONSUMIR 1 CRÉDITO

    try:
        conn = obter_conexao()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE usuarios
            SET creditos = GREATEST(0, creditos - 1)
            WHERE senha = %s
        """, (usuario_valido,))

        conn.commit()

        cursor.close()
        conn.close()

    except Exception as e:
        return jsonify({
            "erro": str(e)
        }), 500

    # DADOS DA SIMULAÇÃO

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

    taxa_mensal = (taxa_juros / 100) / 12

    amortizacao = valor_financiar / prazo_meses

    juros = valor_financiar * taxa_mensal

    primeira_parcela = amortizacao + juros

    comprometimento = renda_total * 0.30

    if primeira_parcela <= comprometimento:

        mensagem = (
            f"🛡️ CERTIFICADO DE VIABILIDADE APROVADO | "
            f"Valor financiado: R$ {valor_financiar:,.2f} | "
            f"Primeira parcela: R$ {primeira_parcela:,.2f} | "
            f"Limite de renda: R$ {comprometimento:,.2f}"
        )

    else:

        mensagem = (
            f"⚠️ CRÉDITO NÃO RECOMENDADO | "
            f"Parcela estimada: R$ {primeira_parcela:,.2f} | "
            f"Limite máximo: R$ {comprometimento:,.2f}"
        )

    return jsonify({
        "mensagem": mensagem
    })

# ===================================
# HOME
# ===================================

@app.route('/')
def home():
    return "Nexus Backend Online"

# ===================================
# INICIAR SERVIDOR
# ===================================

if __name__ == '__main__':

    criar_tabelas()

    app.run(debug=True)

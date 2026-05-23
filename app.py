import os
import uuid
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

# ===================================
# CONEXÃO COM O BANCO
# ===================================

# LOCAL (teste no PC)
# Troque pelos dados do Render se quiser testar localmente
DATABASE_URL = os.environ.get("DATABASE_URL")

# EXEMPLO:
# DATABASE_URL = "postgresql://usuario:senha@host:5432/banco"


def obter_conexao():
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode='require'
    )

    try:
        cursor = conn.cursor()

        # Remove restrição antiga
        cursor.execute("""
            ALTER TABLE usuarios
            DROP CONSTRAINT IF EXISTS usuarios_email_key;
        """)

        # Cria restrição do WhatsApp
        cursor.execute("""
            ALTER TABLE usuarios
            ADD CONSTRAINT usuarios_whatsapp_key UNIQUE (senha);
        """)

        # Cria tabela de indicadores
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

    except Exception:
        conn.rollback()

    return conn


# ===================================
# TOKENS
# ===================================

TOKENS_VALIDOS = {}


# ===================================
# WEBHOOK CADASTRO
# ===================================

@app.route('/api/webhook-registrar', methods=['POST'])
def webhook_registrar():

    dados = request.get_json() or {}

    email = dados.get('email', '')
    nome = dados.get('nome')
    senha = dados.get('senha')
    plano = dados.get('plano', 'Gratuito')
    corretores = dados.get('corretores', '1')

    if not senha or not nome:
        return jsonify({
            "sucesso": False,
            "erro": "Nome e WhatsApp obrigatórios."
        }), 400

    creditos_iniciais = 100 if corretores == 'mais de 3' else 20

    try:

        conn = obter_conexao()

        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            INSERT INTO usuarios
            (email, nome, senha, plano, corretores, creditos)

            VALUES (%s, %s, %s, %s, %s, %s)

            ON CONFLICT (senha)
            DO UPDATE SET
            plano = EXCLUDED.plano,
            corretores = EXCLUDED.corretores,
            creditos = usuarios.creditos + EXCLUDED.creditos

            RETURNING *;
            """,
            (
                email,
                nome,
                senha,
                plano,
                corretores,
                creditos_iniciais
            )
        )

        usuario_salvo = cursor.fetchone()

        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "mensagem": "Usuário salvo com sucesso.",
            "usuario": usuario_salvo
        }), 201

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

    if not email:
        return jsonify({
            "sucesso": False,
            "erro": "E-mail não informado."
        }), 400

    try:

        conn = obter_conexao()

        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )

        if operacao == 'remover':
            quantidade = -abs(quantidade)

        cursor.execute(
            """
            UPDATE usuarios
            SET creditos = GREATEST(0, creditos + %s)
            WHERE email = %s
            RETURNING creditos;
            """,
            (quantidade, email)
        )

        resultado = cursor.fetchone()

        conn.commit()

        cursor.close()
        conn.close()

        if resultado:

            return jsonify({
                "sucesso": True,
                "novos_creditos": resultado['creditos']
            })

        else:

            return jsonify({
                "sucesso": False,
                "erro": "Usuário não encontrado."
            }), 404

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

    if not chave or not valor:

        return jsonify({
            "sucesso": False,
            "erro": "Campos obrigatórios ausentes."
        }), 400

    try:

        conn = obter_conexao()

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO indicadores_mercado
            (chave, valor, fonte, ultima_atualizacao)

            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)

            ON CONFLICT (chave)
            DO UPDATE SET
            valor = EXCLUDED.valor,
            fonte = EXCLUDED.fonte,
            ultima_atualizacao = CURRENT_TIMESTAMP;
            """,
            (chave, str(valor), fonte)
        )

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

        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute("""
            SELECT * FROM indicadores_mercado;
        """)

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
# LOGIN
# ===================================

@app.route('/api/login', methods=['POST'])
def login():

    dados = request.get_json() or {}

    usuario = dados.get('usuario')
    senha = dados.get('senha')

    try:

        conn = obter_conexao()

        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            SELECT * FROM usuarios
            WHERE senha = %s
            """,
            (usuario,)
        )

        usuario_encontrado = cursor.fetchone()

        if usuario_encontrado:

            token = str(uuid.uuid4())

            TOKENS_VALIDOS[token] = usuario

            cursor.execute(
                """
                UPDATE usuarios
                SET token_ativo = %s
                WHERE senha = %s
                """,
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
                "erro": "WhatsApp não encontrado."
            }), 401

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

            cursor = conn.cursor(
                cursor_factory=RealDictCursor
            )

            cursor.execute(
                """
                SELECT senha, creditos
                FROM usuarios
                WHERE token_ativo = %s
                """,
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

        except Exception:
            pass

    if not usuario_valido:

        return jsonify({
            "erro": "Sessão inválida."
        }), 401

    # Consome crédito
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
            "erro": f"Erro ao consumir créditos: {str(e)}"
        }), 500

    # Dados cálculo
    valor_imovel = float(dados.get('valorImovel', 0))
    renda_bruta = float(dados.get('rendaBruta', 0))
    renda_informal = float(dados.get('rendaInformal', 0))
    entrada = float(dados.get('valorEntrada', 0))
    fgts = float(dados.get('valorFgts', 0))
    prazo_meses = int(dados.get('prazoMeses', 360))
    taxa_juros = float(dados.get('taxaJuros', 9.5))

    renda_total = renda_bruta + renda_informal

    valor_financiar = (
        valor_imovel
        - entrada
        - fgts
    )

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

        mensagem = f"""
🛡️ CERTIFICADO DE VIABILIDADE APROVADO

Valor financiado:
R$ {valor_financiar:,.2f}

Primeira parcela:
R$ {primeira_parcela:,.2f}

Limite de renda:
R$ {comprometimento:,.2f}
"""

    else:

        mensagem = f"""
⚠️ CRÉDITO NÃO RECOMENDADO

Parcela estimada:
R$ {primeira_parcela:,.2f}

Limite máximo:
R$ {comprometimento:,.2f}
"""

    return jsonify({
        "mensagem": mensagem
    })


# ===================================
# FRONT-END
# ===================================

@app.route('/')
def home():
    return render_template('index.html')


# ===================================
# INICIAR SERVIDOR
# ===================================

if __name__ == '__main__':
    app.run(debug=True)

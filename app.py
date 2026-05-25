import os
import uuid
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)  # Permite que o CodePen acesse a API sem bloqueios

DATABASE_URL = os.environ.get('DATABASE_URL')
TOKENS_VALIDOS = {}

def obter_conexao():
    # Conecta ao PostgreSQL configurado no ambiente
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def criar_tabelas():
    # Cria a estrutura relacional do NEXUS com as novas regras e Fase 2
    commands = (
        """
        CREATE TABLE IF NOT EXISTS usuarios_corretores (
            id UUID PRIMARY KEY,
            nome_completo VARCHAR(255) NOT NULL,
            cpf_cnpj VARCHAR(14) UNIQUE NOT NULL,
            status VARCHAR(50) DEFAULT 'ativo'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS propostas_credito (
            id UUID PRIMARY KEY,
            comprador_doc VARCHAR(14) NOT NULL,
            vendedor_doc VARCHAR(14) NOT NULL,
            vertical_produto VARCHAR(50) NOT NULL,
            valor_total DECIMAL(15,2) NOT NULL,
            renda_comprovada DECIMAL(15,2) NOT NULL,
            prazo_meses INT NOT NULL,
            banco_escolhido VARCHAR(100),
            status_esteira VARCHAR(50) DEFAULT 'simulacao',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn = None
    try:
        conn = obter_conexao()
        cur = conn.cursor()
        for command in commands:
            cur.execute(command)
        cur.close()
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Erro ao criar tabelas: {error}")
    finally:
        if conn is not None:
            conn.close()

# Executa a criação das tabelas na inicialização do servidor
criar_tabelas()

@app.route('/calcular_credito', methods=['POST'])
def calcular_credito():
    dados = request.get_json()
    
    # Captura e limpeza de dados do payload vindo do Frontend
    vertical = dados.get('vertical', 'imovel')
    valor = float(dados.get('valor', 0))
    renda = float(dados.get('renda', 0))
    prazo = int(dados.get('prazo', 1))
    comprador = dados.get('comprador', '')
    vendedor = dados.get('vendedor', '')
    banco = dados.get('banco', 'Desconhecido')

    # Definição das taxas de juros reais consolidadas
    taxas = {
        'imovel': 0.095,      # 9.5% a.a. (Caixa/Itaú)
        'veiculo': 0.145,     # 14.5% a.a. (Tradicional/Pesados)
        'agro': 0.085,        # 8.5% a.a. (Plano Safra BB)
        'global': 0.055       # 5.5% a.a. (Moeda Estrangeira/Cross-Border)
    }
    juros_anual = taxas.get(vertical, 0.095)
    juros_mensal = (1 + jurosAnual) ** (1/12) - 1 if vertical != 'global' else juros_anual / 12

    # Lógica de cálculo baseada no sistema Price/SAC
    parcela_price = (valor * juros_mensal) / (1 - (1 + juros_mensal) ** (-prazo)) if juros_mensal > 0 else valor / prazo
    parcela_sac_inicial = (valor / prazo) + (valor * juros_mensal)
    
    parcela_referencia = parcela_sac_inicial if vertical == 'imovel' else parcela_price
    comprometimento = (parcela_referencia / renda) * 100 if renda > 0 else 100

    # Gravação imediata do histórico de simulação no PostgreSQL
    proposta_id = str(uuid.uuid4())
    status_esteira = "aprovado" if comprometimento <= 30 else "recusado"

    try:
        conn = obter_conexao()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO propostas_credito (id, comprador_doc, vendedor_doc, vertical_produto, valor_total, renda_comprovada, prazo_meses, banco_escolhido, status_esteira)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (proposta_id, comprador, vendedor, vertical, valor, renda, prazo, banco, status_esteira)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao salvar proposta: {e}")

    # Retorno estruturado da API para o Frontend do NEXUS
    return jsonify({
        "proposta_id": proposta_id,
        "status": status_esteira,
        "comprometimento": round(comprometimento, 1),
        "taxa_anual": round(juros_anual * 100, 1),
        "parcela_price": round(parcela_price, 2),
        "parcela_sac": round(parcela_sac_inicial, 2),
        "parcela_referencia": round(parcela_referencia, 2)
    })

@app.route('/')
def home():
    return "NEXUS Core API - Servidor Ativo e Operando"

if __name__ == '__main__':
    app.run(debug=True)

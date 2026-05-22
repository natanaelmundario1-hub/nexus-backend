import os
import uuid
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def obter_conexao_banco():
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não foi configurada no Render.")
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def inicializar_banco_dados():
    try:
        conn = obter_conexao_banco()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                email VARCHAR(150) PRIMARY KEY,
                senha VARCHAR(100) NOT NULL,
                nome VARCHAR(100)
            );
        """)
        
        cursor.execute("SELECT COUNT(*) FROM usuarios;")
        if cursor.fetchone() == 0:
            cursor.execute("""
                INSERT INTO usuarios (email, senha, nome) VALUES 
                ('natanael@email.com', 'nexusSoberano2026', 'Natanael'),
                ('jhonn@email.com', 'filhoDoNata123', 'Jhonn'),
                ('cliente01@email.com', 'creditoNexus456', 'Cliente de Teste');
            """)
            
        conn.commit()
        cursor.close()
        conn.close()
        print("🏛️ Banco de dados PostgreSQL inicializado com sucesso.")
    except Exception as e:
        print(f"❌ Erro ao inicializar o banco: {e}")

if DATABASE_URL:
    inicializar_banco_dados()

TOKENS_VALIDOS = {}

def buscar_taxa_veiculos_bacen():
    try:
        url = "https://bcb.gov.br"
        resposta = requests.get(url, timeout=5)
        dados = resposta.json()
        registro = dados['value'][0]
        taxa_mensal = float(registro['TaxaJurosMensal']) / 100
        taxa_anual = float(registro['TaxaJurosAnual'])
        nome_banco = registro['InstituicaoFinanceira']
        return {"sucesso": True, "taxa_mensal": taxa_mensal, "taxa_anual": taxa_anual, "referencia": nome_banco}
    except Exception as e:
        return {"sucesso": False, "taxa_mensal": 0.0165, "taxa_anual": 21.6, "referencia": "Taxa Estimada Praticada pelo Mercado"}

@app.route('/api/login', methods=['POST'])
def login():
    dados = request.get_json() or {}
    usuario = dados.get('usuario', '').strip().lower()
    senha = dados.get('senha', '').strip()
    try:
        conn = obter_conexao_banco()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM usuarios WHERE email = %s AND senha = %s;", (usuario, senha))
        registro = cursor.fetchone()
        cursor.close()
        conn.close()
        if registro:
            token = str(uuid.uuid4())
            TOKENS_VALIDOS[token] = usuario
            return jsonify({"sucesso": True, "token": token, "nome": registro['nome']})
        else:
            return jsonify({"sucesso": False, "erro": "Acesso negado: dados incorretos."})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)})

@app.route('/api/calcular-credito', methods=['POST'])
def calcular_credito():
    dados = request.get_json() or {}
    token = dados.get('token')
    if not token or token not in TOKENS_VALIDOS:
        return jsonify({"erro": "Sessão inválida."}), 401
    
    valor_imovel = dados.get('valorImovel', 0)
    renda_bruta = dados.get('rendaBruta', 0)
    renda_informal = dados.get('rendaInformal', 0)
    entrada = dados.get('valorEntrada', 0)
    fgts = dados.get('valorFgts', 0)
    prazo_meses = dados.get('prazoMeses', 360)
    taxa_juros_anual = dados.get('taxaJuros', 9.5)
    
    renda_total = renda_bruta + renda_informal
    valor_financiar = valor_imovel - entrada - fgts
    
    nota_legal = "\n\n----------------------------------------\n* NOTA INFORMATIVA: Simulação informativa preliminar. Aprovação final depende da instituição financeira."
    
    if valor_financiar <= 0:
        return jsonify({"mensagem": f"Simulação Concluída! O valor de entrada cobre o imóvel.{nota_legal}"})
    
    taxa_mensal = (taxa_juros_anual / 100) / 12
    amortizacao_mensal = valor_financiar / prazo_meses
    juros_primeira_parcela = valor_financiar * taxa_mensal
    primeira_parcela_estimada = amortizacao_mensal + juros_primeira_parcela
    comprometimento_permitido = renda_total * 0.30
    
    if primeira_parcela_estimada <= Fire_comprometimento_permitido:
        mensagem = f"🛡️ CERTIFICADO DE VIABILIDADE APROVADO\n\nValor a financiar: R$ {valor_financiar:,.2f}\nPrazo: {prazo_meses} meses\nTaxa: {taxa_juros_anual}% a.a.\nPrimeira parcela: R$ {primeira_parcela_estimada:,.2f}{nota_legal}"
    else:
        mensagem = f"⚠️ ALERTA DE RESTRIÇÃO DE CRÉDITO\n\nParcela inicial (R$ {primeira_parcela_estimada:,.2f}) ultrapassa 30% da renda ({comprometimento_permitido:,.2f}).{nota_legal}"
        
    return jsonify({"mensagem": mensagem})

if __name__ == '__main__':
    porta = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=porta)

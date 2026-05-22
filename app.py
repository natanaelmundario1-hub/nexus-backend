import os
import uuid
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
# Libera o acesso para o seu CodePen / GitHub Pages enviar dados para cá
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def obter_conexao_banco():
    """Estabelece uma conexão direta com o banco de dados PostgreSQL."""
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não foi configurada no Render.")
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def inicializar_banco_dados():
    """Cria as tabelas necessárias no banco automaticamente caso elas não existam."""
    try:
        conn = obter_conexao_banco()
        cursor = conn.cursor()
        
        # 1. Cria a tabela de usuários autorizados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                email VARCHAR(150) PRIMARY KEY,
                senha VARCHAR(100) NOT NULL,
                nome VARCHAR(100)
            );
        """)
        
        # 2. Insere alguns usuários de teste padrão se a tabela estiver vazia
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
        print(f"❌ Erro ao inicializar o banco de dados: {e}")

# Inicializa o banco assim que o servidor Python liga na nuvem
if DATABASE_URL:
    inicializar_banco_dados()

# Dicionário em memória para gerenciar sessões ativas (Tokens temporários)
TOKENS_VALIDOS = {}

# ==========================================
# 🤖 MÓDULO ROBÔ: TAXAS DO BANCO CENTRAL EM TEMPO REAL
# ==========================================
def buscar_taxa_veiculos_bacen():
    """Consulta a API oficial de Dados Abertos do Banco Central do Brasil para obter as taxas atuais."""
    try:
        url = "https://bcb.gov.br"
        
        resposta = requests.get(url, timeout=5)
        dados = resposta.json()
        
        registro = dados['value']
        taxa_mensal = float(registro['TaxaJurosMensal']) / 100
        taxa_anual = float(registro['TaxaJurosAnual'])
        nome_banco = registro['InstituicaoFinanceira']
        
        return {
            "sucesso": True,
            "taxa_mensal": taxa_mensal,
            "taxa_anual": taxa_anual,
            "referencia": nome_banco
        }
    except Exception as e:
        print(f"⚠️ Alerta: Falha ao consultar API do Banco Central ({e}). Usando taxa de segurança.")
        return {
            "sucesso": False,
            "taxa_mensal": 0.0165,
            "taxa_anual": 21.6,
            "referencia": "Taxa Estimada Praticada pelo Mercado"
        }

# ==========================================
# 🔐 ROTAS DA API: AUTENTICAÇÃO E LOGIN
# ==========================================
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
            return jsonify({"sucesso": False, "erro": "Acesso negado: Usuário não cadastrado ou senha incorreta."})
            
    except Exception as e:
        return jsonify({"sucesso": False, "erro": f"Erro interno de conexão com o banco: {str(e)}"})

# ==========================================
# 🧮 ROTAS DA API: MOTORES DE SIMULAÇÃO
# ==========================================
@app.route('/api/calcular-credito', methods=['POST'])
def calcular_credito():
    dados = request.get_json() or {}
    token = dados.get('token')
    
    if not token or token not in TOKENS_VALIDOS:
        return jsonify({"erro": "Sessão inválida ou não autorizada. Faça login novamente."}), 401
    
    valor_imovel = dados.get('valorImovel', 0)
    renda_bruta = dados.get('rendaBruta', 0)
    renda_informal = dados.get('rendaInformal', 0)
    entrada = dados.get('valorEntrada', 0)
    fgts = dados.get('valorFgts', 0)
    prazo_meses = dados.get('prazoMeses', 360)
    taxa_juros_anual = dados.get('taxaJuros', 9.5)
    
    renda_total = renda_bruta + renda_informal
    valor_financiar = valor_imovel - entrada - fgts
    
    nota_legal = "\n\n----------------------------------------\n* NOTA INFORMATIVA: Este documento constitui uma simulação informativa e preliminar de viabilidade com base nas tabelas vigentes. Os valores e a aprovação final do crédito dependem exclusivamente da análise cadastral e das regras de compliance da instituição financeira escolhida."
    
    if valor_financiar <= 0:
        return jsonify({
            "mensagem": f"Simulação Concluída! O valor de entrada e saldo do FGTS cobrem integralmente o custo do imóvel. Não há saldo residual a financiar.{nota_legal}"
        })
    
    taxa_mensal = (taxa_juros_anual / 100) / 12
    amortizacao_mensal = valor_financiar / prazo_meses
    juros_primeira_parcela = valor_financiar * taxa_mensal
    primeira_parcela_estimada = amortizacao_mensal + juros_primeira_parcela
    
    comprometimento_permitido = renda_total * 0.30
    
    if primeira_parcela_estimada <= comprometimento_permitido:
        mensagem = (
            f"🛡️ CERTIFICADO DE VIABILIDADE APROVADO\n\n"
            f"Valor total a financiar: R$ {valor_financiar:,.2f}\n"
            f"Prazo contratado: {prazo_meses} meses\n"
            f"Taxa de juros aplicada: {taxa_juros_anual}% ao ano\n"
            f"Primeira parcela estimada: R$ {primeira_parcela_estimada:,.2f}\n\n"
            f"O perfil atende aos critérios iniciais de comprometimento de renda (limite prudencial de 30% da renda = R$ {comprometimento_permitido:,.2f})."
            f"{nota_legal}"
        )
    else:
        mensagem = (
            f"⚠️ ALERTA DE RESTRIÇÃO DE CRÉDITO\n\n"
            f"O valor solicitado para financiamento (R$ {valor_financiar:,.2f}) gera uma parcela inicial estimada de R$ {primeira_parcela_estimada:,.2f}.\n"
            f"Isso ultrapassa o limite prudencial de 30% da renda mensal informada (R$ {comprometimento_permitido:,.2f}).\n\n"
            f"Sugestão técnica: Incremente o valor de entrada em dinheiro ou amplie o prazo de amortização para diluir a parcela."
            f"{nota_legal}"
        )
        
    return jsonify({"mensagem": mensagem})

@app.route('/api/calcular-veiculo', methods=['POST'])
def calcular_veiculo():
    dados = request.get_json() or {}
    token = dados.get('token')
    
    if not token or token not in TOKENS_VALIDOS:
        return jsonify({"erro": "Sessão inválida ou não autorizada."}), 401
        
    valor_veiculo = dados.get('valorVeiculo', 0)
    valor_entrada = dados.get('valorEntrada', 0)
    prazo_meses = dados.get('prazoMeses', 48)
    
    valor_financiar = valor_veiculo - valor_entrada
    
    if valor_financiar <= 0:
        return jsonify({"mensagem": "A entrada cobre o valor total do veículo."})
        
    dados_taxa = buscar_taxa_veiculos_bacen()
    i = dados_taxa['taxa_mensal']
    
    try:
        parcela_price = valor_financiar * (i * (1 + i)**prazo_meses) / ((1 + i)**prazo_meses - 1)
    except ZeroDivisionError:
        parcela_price = valor_financiar / prazo_meses
        
    nota_legal = "\n\n----------------------------------------\n* NOTA INFORMATIVA: Simulação veicular baseada em médias mercadológicas informadas pelo Banco Central do Brasil. Os juros e condições reais variam conforme o score do CPF do cliente na financeira."
        
    mensagem = (
        f"🚗 SIMULAÇÃO DE CRÉDITO VEICULAR (TABELA PRICE)\n\n"
        f"Valor do Veículo: R$ {valor_veiculo:,.2f}\n"
        f"Total a Financiar: R$ {valor_financiar:,.2f}\n"
        f"Prazo Selecionado: {prazo_meses} parcelas fixas\n"
        f"Taxa do Banco Central capturada: {dados_taxa['taxa_anual']:.2f}% ao ano\n"
        f"Origem da Taxa de Mercado: {dados_taxa['referencia']}\n\n"
        f"👉 PARCELA FIXA ESTIMADA: {prazo_meses}x de R$ {parcela_price:,.2f}"
        f"{nota_legal}"
    )
    
    return jsonify({"mensagem": mensagem})

if __name__ == '__main__':
    porta = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=porta)

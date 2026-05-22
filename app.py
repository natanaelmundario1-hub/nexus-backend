import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Libera o acesso para o seu CodePen / GitHub Pages enviar dados para cá
CORS(app)

# 🔐 BANCO DE USUÁRIOS AUTORIZADOS
# Você e seu filho podem adicionar, remover ou alterar os acessos aqui:
USUARIOS_CADASTRADOS = {
    "natanael@email.com": "nexusSoberano2026",
    "jhonn@email.com": "filhoDoNata123",
    "cliente01@email.com": "creditoNexus456"
}

# Dicionário em memória para controlar quem está logado temporariamente
TOKENS_VALIDOS = {}

@app.route('/api/login', methods=['POST'])
def login():
    dados = request.get_json() or {}
    usuario = dados.get('usuario', '').strip()
    senha = dados.get('senha', '').strip()
    
    # O Python verifica se o usuário existe na lista E se a senha confere
    if usuario in USUARIOS_CADASTRADOS and USUARIOS_CADASTRADOS[usuario] == senha:
        # Cria um código de sessão único e seguro para este usuário
        token = str(uuid.uuid4())
        TOKENS_VALIDOS[token] = usuario
        return jsonify({"sucesso": True, "token": token})
    else:
        return jsonify({
            "sucesso": False, 
            "erro": "Acesso negado: Usuário não possui cadastro ativo ou dados incorretos."
        })

@app.route('/api/calcular-credito', methods=['POST'])
def calcular_credito():
    dados = request.get_json() or {}
    token = dados.get('token')
    
    # Bloqueio direto: se o token não for válido, não faz a conta de jeito nenhum
    if not token or token not in TOKENS_VALIDOS:
        return jsonify({"erro": "Sessão inválida ou não autorizada. Faça login novamente."}), 401
    
    # Captura os dados numéricos enviados do site
    valor_imovel = dados.get('valorImovel', 0)
    renda_bruta = dados.get('rendaBruta', 0)
    renda_informal = dados.get('rendaInformal', 0)
    entrada = dados.get('valorEntrada', 0)
    fgts = dados.get('valorFgts', 0)
    prazo_meses = dados.get('prazoMeses', 360)
    taxa_juros_anual = dados.get('taxaJuros', 9.5)
    
    # Regras do Motor de Cálculo Financeiro
    renda_total = renda_bruta + renda_informal
    valor_financiar = valor_imovel - entrada - fgts
    
    if valor_financiar <= 0:
        return jsonify({
            "mensagem": "Simulação Concluída! O valor de entrada e saldo do FGTS cobrem integralmente o custo do imóvel. Não há saldo residual a financiar."
        })
    
    # Cálculo das parcelas (Modelo SAC aproximado)
    taxa_mensal = (taxa_juros_anual / 100) / 12
    amortizacao_mensal = valor_financiar / prazo_meses
    juros_primeira_parcela = valor_financiar * taxa_mensal
    primeira_parcela_estimada = amortizacao_mensal + juros_primeira_parcela
    
    # Limite prudencial de 30% da renda do cliente
    comprometimento_permitido = renda_total * 0.30
    
    if primeira_parcela_estimada <= compromised_permitido:
        mensagem = (
            f"🛡️ CERTIFICADO DE VIABILIDADE APROVADO\n\n"
            f"Valor total a financiar: R$ {valor_financiar:,.2f}\n"
            f"Prazo contratado: {prazo_meses} meses\n"
            f"Taxa de juros aplicada: {taxa_juros_anual}% ao ano\n"
            f"Primeira parcela estimada: R$ {primeira_parcela_estimada:,.2f}\n\n"
            f"O perfil atende aos critérios iniciais de comprometimento de renda (limite de 30% = R$ {comprometimento_permitido:,.2f})."
        )
    else:
        mensagem = (
            f"⚠️ ALERTA DE RESTRIÇÃO DE CRÉDITO\n\n"
            f"O valor solicitado para financiamento (R$ {valor_financiar:,.2f}) gera uma parcela inicial estimada de R$ {primeira_parcela_estimada:,.2f}.\n"
            f"Isso ultrapassa o limite prudencial de 30% da renda mensal comprovada (R$ {comprometimento_permitido:,.2f}).\n\n"
            f"Sugestão técnica: Incremente o valor de entrada em dinheiro ou amplie o prazo de amortização."
        )
        
    return jsonify({"mensagem": mensagem})

if __name__ == '__main__':
    # Roda o servidor na porta 5000 localmente
    app.run(debug=True, port=5000)

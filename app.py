import os
import uuid
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')
# DEFINA A SUA SENHA MASTER DE ACESSO AO PAINEL AQUI
SENHA_ADMIN = "NEXUS2026"

def obter_conexao():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode='require'
    )

def criar_tabelas():
    comandos = (
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
        """,
    )
    conn = None
    try:
        conn = obter_conexao()
        cur = conn.cursor()
        for comando in comandos:
            cur.execute(comando)
        conn.commit()
        cur.close()
        print("Banco de dados sincronizado.")
    except Exception as e:
        print("Erro ao criar tabelas:", e)
    finally:
        if conn:
            conn.close()

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "sistema": "NEXUS Core FinTech API"
    })
@app.route('/calcular_credito', methods=['POST'])
def calcular_credito():
    dados = request.get_json() or {}
    try:
        vertical = dados.get('vertical', 'imovel')
        nome_cliente = dados.get('nome_cliente', '').upper()
        whatsapp = dados.get('whatsapp', '').replace('(', '').replace(')', '').replace(' ', '').replace('-', '')
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

        ultimo_digito = comprador[-1] if comprador else "0"
        if ultimo_digito in ['0', '2', '4', '6', '8'] or vertical == 'multas':
            score_interno = 780
            status_esteira = "aprovado"
        else:
            score_interno = 320
            status_esteira = "recusado"

        taxas = {'imovel': 0.095, 'veiculo': 0.145, 'agro': 0.085, 'global': 0.055, 'multas': 0.000}
        juros_anual = taxas.get(vertical, 0.095)
        
        if vertical == 'global':
            juros_mensal = juros_anual / 12
        elif vertical == 'multas' and forma_pagamento == 'boleto':
            juros_mensal = 0.045
            juros_anual = ((1 + juros_mensal) ** 12) - 1
        else:
            juros_mensal = ((1 + juros_anual) ** (1 / 12)) - 1

        valor_financ = (valor - entrada) if vertical == 'multas' else valor
        if juros_mensal > 0 and prazo > 0:
            p_price = (valor_financ * juros_mensal) / (1 - (1 + juros_mensal) ** (-prazo))
        else:
            p_price = valor_financ / prazo if prazo > 0 else valor_financ

        p_sac = (valor_financ / prazo) + (valor_financ * juros_mensal) if prazo > 0 else valor_financ
        p_ref = p_sac if vertical === 'imovel' else p_price
        
        if status_esteira == "aprovado" and vertical != 'multas' and vertical != 'score':
            comp = (p_ref / renda) * 100 if renda > 0 else 0
            if comp > 30:
                status_esteira = "recusado"

        proposta_id = str(uuid.uuid4())
        try:
            conn = obter_conexao()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO propostas_credito (
                    id, nome_cliente, whatsapp_cliente, comprador_doc, vendedor_doc, data_nascimento,
                    vertical_produto, sub_produto, valor_total, renda_comprovada, prazo_meses,
                    banco_escolhido, placa_veiculo, renavam_veiculo, valor_entrada, status_esteira, score_calculado
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (proposta_id, nome_cliente, whatsapp, comprador, vendedor, data_nascimento,
                  vertical, sub_produto, valor, renda, prazo, banco, placa, renavam, entrada, status_esteira, score_interno))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as edb:
            print("Erro Postgres:", edb)

        return jsonify({
            "sucesso": True, "proposta_id": proposta_id, "status": status_esteira, "score_cliente": score_interno,
            "taxa_anual": round(juros_anual * 100, 2), "taxa_mensal": round(juros_mensal * 100, 4),
            "parcela_price": round(p_price, 2), "parcela_sac": round(p_sac, 2), "parcela_referencia": round(p_ref, 2)
        })
    except Exception as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 500

# =========================================================
# API ENDPOINT: FAZ A LEITURA DAS FICHAS DE CLIENTES DO BANCO
# =========================================================
@app.route('/api/propostas', methods=['GET'])
def api_propostas():
    senha = request.args.get('senha', '')
    if senha != SENHA_ADMIN:
        return jsonify({"erro": "Acesso negado"}), 401
    try:
        conn = obter_conexao()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT nome_cliente, whatsapp_cliente, vertical_produto, valor_total, prazo_meses, status_esteira, criado_em FROM propostas_credito ORDER BY criado_em DESC LIMIT 100;")
        linhas = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(linhas)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# =========================================================
# INTERFACE DO PAINEL ADMINISTRATIVO (DASHBOARD FINTECH)
# =========================================================
@app.route('/painel')
def painel_administrativo():
    html_dashboard = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NEXUS Admin - Painel do Dono</title>
        <meta charset="utf-8">
        <style>
            body { background: #020617; color: white; font-family: sans-serif; padding: 30px; margin: 0; }
            .container { max-width: 1100px; margin: auto; }
            h2 { color: #0284c7; border-bottom: 1px solid #1e293b; padding-bottom: 10px; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; background: #0f172a; border-radius: 8px; overflow: hidden; }
            th, td { padding: 12px 15px; text-align: left; font-size: 13px; border-bottom: 1px solid #1e293b; }
            th { background: #1e293b; color: #94a3b8; text-transform: uppercase; font-size: 11px; }
            .status-aprovado { color: #10b981; font-weight: bold; background: #061f14; padding: 4px 8px; border-radius: 4px; }
            .status-recusado { color: #ef4444; font-weight: bold; background: #2d0f0f; padding: 4px 8px; border-radius: 4px; }
            .btn-whats { background: #10b981; color: black; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold; cursor: pointer; text-decoration: none; font-size: 11px; }
            .btn-whats:hover { background: #059669; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🏆 NEXUS | Central do Dono - Monitoramento de Leads</h2>
            <div id="status-conexao" style="color: #94a3b8; font-size: 13px;">Carregando banco de dados...</div>
            <table id="tabela-leads">
                <thead>
                    <tr>
                        <th>Data/Hora</th>
                        <th>Nome do Cliente</th>
                        <th>Vertical</th>
                        <th>Valor Total</th>
                        <th>Prazo</th>
                        <th>Status</th>
                        <th>Ação Comercial</th>
                    </tr>
                </thead>
                <tbody id="corpo-tabela">
                    <!-- Fichas injetadas automaticamente -->
                </tbody>
            </table>
        </div>
        <script>
            var senhaMaster = prompt("Digite a Senha Master da Nexus:");
            fetch('/api/propostas?senha=' + senhaMaster)
            .then(res => {
                if(!res.ok) { alert("Senha incorreta!"); document.getElementById('status-conexao').innerText = "Acesso Negado."; return; }
                return res.json();
            })
            .then(dados => {
                document.getElementById('status-conexao').innerText = "Conectado. Exibindo os últimos " + dados.length + " atendimentos.";
                var corpo = document.getElementById('corpo-tabela');
                dados.forEach(p => {
                    var dataFormatada = new Date(p.criado_em).toLocaleString('pt-BR');
                    var valorMoeda = parseFloat(p.valor_total).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
                    var classStatus = p.status_esteira === 'aprovado' ? 'status-aprovado' : 'status-recusado';
                    
                    var linkWhats = "https://whatsapp.com" + p.whatsapp_cliente + "&text=Olá " + p.nome_cliente + ", vi sua simulação de " + p.vertical_produto.toUpperCase() + " na Nexus. Vamos finalizar sua contratação?";
                    
                    var tr = document.createElement('tr');
                    tr.innerHTML = "<td>" + dataFormatada + "</td>" +
                                   "<td><strong>" + p.nome_cliente + "</strong></td>" +
                                   "<td>" + p.vertical_produto.toUpperCase() + "</td>" +
                                   "<td>" + valorMoeda + "</td>" +
                                   "<td>" + p.prazo_meses + "x</td>" +
                                   "<td><span class='" + classStatus + "'>" + p.status_esteira.toUpperCase() + "</span></td>" +
                                   "<td><a href='" + linkWhats + "' target='_blank' class='btn-whats'>🟢 Chamar no Whats</a></td>";
                    corpo.appendChild(tr);
                });
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html_dashboard)

if __name__ == '__main__':
    criar_tabelas()
    app.run(debug=True, host='0.0.0.0', port=5000)

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
import io
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import schedule
import time
import threading

# --- 1. CONFIGURAÇÃO INICIAL E CSS ---
st.set_page_config(page_title="ERP TI - Login", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

# --- 2. CONTROLE DE SESSÃO (LOGIN) ---
if 'logado' not in st.session_state:
    st.session_state['logado'] = False

# SE O USUÁRIO NÃO ESTIVER LOGADO, MOSTRA APENAS A TELA DE LOGIN
if not st.session_state['logado']:
    st.title("🔒 Acesso ao Sistema WorkFlow TI")
    st.markdown("Por favor, identifique-se para acessar o ERP e habilitar o envio de relatórios.")
    
    col1, col2, col3 = st.columns([1, 2, 1]) # Centraliza o formulário na tela
    with col2:
        with st.container(border=True):
            with st.form("form_login"):
                st.markdown("### Credenciais de Acesso")
                email_input = st.text_input("E-mail Corporativo")
                senha_input = st.text_input("Senha de App (SMTP)", type="password")
                
                if st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True):
                    if email_input and senha_input:
                        # Salva na memória da sessão
                        st.session_state['email_usuario'] = email_input
                        st.session_state['senha_usuario'] = senha_input
                        st.session_state['logado'] = True
                        st.rerun() # Recarrega a página para sumir com o login
                    else:
                        st.error("⚠️ Preencha o e-mail e a senha para continuar.")

# SE ESTIVER LOGADO, RODA O SISTEMA COMPLETO
else:
    # --- 3. BANCO DE DADOS ---
    conn = sqlite3.connect('banco_gestao_ti.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS colaboradores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, cargo TEXT, status TEXT DEFAULT 'Presencial');
        CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, empresa TEXT NOT NULL, contato TEXT, email TEXT);
        CREATE TABLE IF NOT EXISTS projetos (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, cliente_id INTEGER, sprint_atual TEXT, status TEXT DEFAULT 'Ativo');
        CREATE TABLE IF NOT EXISTS chamados (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL, projeto_id INTEGER, colaborador_id INTEGER, tipo TEXT, status TEXT DEFAULT 'Backlog');
    ''')
    conn.commit()

    def carregar_tabela(nome_tabela): return pd.read_sql_query(f'SELECT * FROM {nome_tabela}', conn)
    def salvar_alteracoes(df_editado, nome_tabela): df_editado.to_sql(nome_tabela, conn, if_exists='replace', index=False)

    df_colaboradores = carregar_tabela('colaboradores')
    df_clientes = carregar_tabela('clientes')
    df_projetos = carregar_tabela('projetos')
    df_chamados = carregar_tabela('chamados')

    # --- 4. FUNÇÕES DE EXPORTAÇÃO E E-MAIL ---
    def gerar_excel():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_chamados.to_excel(writer, sheet_name='Chamados', index=False)
            df_projetos.to_excel(writer, sheet_name='Projetos', index=False)
        return output.getvalue()

    def gerar_pdf():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt="Relatório Executivo - WorkFlow TI", ln=True, align='C')
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='C')
        pdf.ln(10)
        pdf.cell(200, 10, txt=f"Total de Projetos: {len(df_projetos)}", ln=True)
        pdf.cell(200, 10, txt=f"Chamados Pendentes: {len(df_chamados[df_chamados['status'] != 'Done'])}", ln=True)
        pdf.ln(10)
        pdf.cell(200, 10, txt="-- Detalhamento de Chamados --", ln=True)
        for index, row in df_chamados.iterrows():
            pdf.cell(200, 10, txt=f"[{row['status']}] {row['titulo']} (Tipo: {row['tipo']})", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    # AGORA USA AS CREDENCIAIS DA SESSÃO!
    def enviar_email(destinatario, assunto, mensagem, anexo_pdf=None, remetente=None, senha=None):
        email_from = remetente if remetente else st.session_state['email_usuario']
        senha_app = senha if senha else st.session_state['senha_usuario']

        msg = MIMEMultipart()
        msg['From'] = email_from
        msg['To'] = destinatario
        msg['Subject'] = assunto
        msg.attach(MIMEText(mensagem, 'plain'))

        if anexo_pdf:
            part = MIMEApplication(anexo_pdf, Name="Relatorio_TI.pdf")
            part['Content-Disposition'] = 'attachment; filename="Relatorio_TI.pdf"'
            msg.attach(part)

        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(email_from, senha_app)
            server.send_message(msg)
            server.quit()
            return True, "E-mail enviado com sucesso!"
        except Exception as e:
            return False, f"Falha na autenticação ou envio: Verifique sua Senha de App. Erro: {e}"

    # --- 5. THREAD DE AGENDAMENTO ---
    def rodar_agendador():
        while True:
            schedule.run_pending()
            time.sleep(30)

    if 'agendador_iniciado' not in st.session_state:
        threading.Thread(target=rodar_agendador, daemon=True).start()
        st.session_state['agendador_iniciado'] = True

    # Recebe as credenciais para que a Thread em background consiga enviar
    def tarefa_agendada(destinatario, remetente, senha):
        pdf_bytes = gerar_pdf()
        enviar_email(destinatario, "Relatório Diário Automático", "Segue o relatório atualizado.", pdf_bytes, remetente, senha)

    # --- 6. MENU LATERAL EXECUTIVO ---
    with st.sidebar:
        st.markdown("## 💠 **WorkFlow TI**")
        st.markdown(f"👤 *Logado como: {st.session_state['email_usuario']}*")
        
        if st.button("Sair (Logout)"):
            st.session_state['logado'] = False
            st.rerun()
            
        st.markdown("---")
        menu = st.radio(
            "Navegação:", 
            ["📊 Dashboard", "👥 Equipe", "🏢 Clientes", "📂 Projetos", "🎫 Kanban", "🚀 Relatórios & Automação"]
        )

    # --- 7. TELAS DO SISTEMA ---
    
    if menu == "📊 Dashboard":
        st.title("Visão Geral Executiva")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Colaboradores Ativos", len(df_colaboradores))
        col2.metric("Clientes no Portfólio", len(df_clientes))
        col3.metric("Projetos em Andamento", len(df_projetos))
        col4.metric("Chamados em Aberto", len(df_chamados[df_chamados['status'] != 'Done']))
        
        st.divider()
        st.subheader("📈 Análise de Operação")
        graf_col1, graf_col2 = st.columns(2)
        
        with graf_col1:
            with st.container(border=True):
                st.markdown("**Distribuição de Chamados por Status**")
                if not df_chamados.empty:
                    contagem_status = df_chamados['status'].value_counts().reset_index()
                    contagem_status.columns = ['Status', 'Quantidade']
                    fig_status = px.pie(contagem_status, names='Status', values='Quantidade', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                    fig_status.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                    st.plotly_chart(fig_status, use_container_width=True)
                else:
                    st.info("Sem dados suficientes.")

        with graf_col2:
            with st.container(border=True):
                st.markdown("**Tipos de Demandas**")
                if not df_chamados.empty:
                    contagem_tipo = df_chamados['tipo'].value_counts().reset_index()
                    contagem_tipo.columns = ['Tipo', 'Quantidade']
                    fig_tipo = px.bar(contagem_tipo, x='Tipo', y='Quantidade', text='Quantidade', color='Tipo', color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig_tipo.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300, showlegend=False)
                    st.plotly_chart(fig_tipo, use_container_width=True)
                else:
                    st.info("Sem dados suficientes.")

    elif menu == "👥 Equipe":
        st.header("Gestão de Equipe e Alocação")
        df_equipe_editado = st.data_editor(df_colaboradores, num_rows="dynamic", use_container_width=True, column_config={"status": st.column_config.SelectboxColumn("Status", options=["Presencial", "Remoto", "Férias", "Ausente"])}, key="ed_eq")
        if st.button("Gravar Alterações", type="primary"): salvar_alteracoes(df_equipe_editado, 'colaboradores'); st.rerun()

    elif menu == "🏢 Clientes":
        st.header("Portfólio de Clientes")
        df_clientes_editado = st.data_editor(df_clientes, num_rows="dynamic", use_container_width=True, key="ed_cli")
        if st.button("Gravar Alterações", type="primary"): salvar_alteracoes(df_clientes_editado, 'clientes'); st.rerun()

    elif menu == "📂 Projetos":
        st.header("Gestão de Projetos e Sprints")
        lista_clientes = df_clientes['id'].astype(str).tolist() if not df_clientes.empty else ["0"]
        df_projetos_editado = st.data_editor(df_projetos, num_rows="dynamic", use_container_width=True, column_config={"cliente_id": st.column_config.SelectboxColumn("ID Cliente", options=lista_clientes), "status": st.column_config.SelectboxColumn("Fase", options=["Planejamento", "Ativo", "Concluído"])}, key="ed_proj")
        if st.button("Gravar Alterações", type="primary"): salvar_alteracoes(df_projetos_editado, 'projetos'); st.rerun()

    elif menu == "🎫 Kanban":
        st.header("Kanban de Operações")
        lista_projetos = df_projetos['id'].astype(str).tolist() if not df_projetos.empty else ["0"]
        lista_equipe = df_colaboradores['id'].astype(str).tolist() if not df_colaboradores.empty else ["0"]

        with st.expander("⚙️ Gerenciar Chamados", expanded=False):
            df_chamados_editado = st.data_editor(df_chamados, num_rows="dynamic", use_container_width=True, column_config={"projeto_id": st.column_config.SelectboxColumn("ID Projeto", options=lista_projetos), "colaborador_id": st.column_config.SelectboxColumn("ID Resp.", options=lista_equipe), "tipo": st.column_config.SelectboxColumn("Tipo", options=["Feature", "Bug", "Suporte", "Infra"]), "status": st.column_config.SelectboxColumn("Estágio", options=["Backlog", "Doing", "Review", "Done"])}, key="ed_cham")
            if st.button("Atualizar Chamados", type="primary"): salvar_alteracoes(df_chamados_editado, 'chamados'); st.rerun()

        st.markdown("### Fluxo de Trabalho")
        if not df_chamados.empty:
            c1, c2, c3, c4 = st.columns(4)
            fases = [("Backlog", c1, "📋"), ("Doing", c2, "💻"), ("Review", c3, "🔍"), ("Done", c4, "✅")]
            for fase, coluna, icone in fases:
                with coluna:
                    with st.container(border=True):
                        st.markdown(f"**{icone} {fase}**")
                        st.divider()
                        chamados_fase = df_chamados[df_chamados['status'] == fase]
                        for _, row in chamados_fase.iterrows():
                            with st.container(border=True):
                                st.markdown(f"**{row['titulo']}**")
                                st.caption(f"{row['tipo']} | Resp: {row['colaborador_id']}")

    elif menu == "🚀 Relatórios & Automação":
        st.title("Exportação, E-mails e Automação")
        tab1, tab2, tab3 = st.tabs(["📥 Exportar Arquivos", "📧 Enviar E-mail Avulso", "⏰ Agendamento Automático"])

        with tab1:
            st.subheader("Baixar Arquivos")
            col1, col2 = st.columns(2)
            with col1: st.download_button(label="📊 Baixar Excel", data=gerar_excel(), file_name="Dados_TI.xlsx", mime="application/vnd.ms-excel", type="primary")
            with col2: st.download_button(label="📄 Baixar PDF", data=gerar_pdf(), file_name="Relatorio_TI.pdf", mime="application/pdf", type="primary")

        with tab2:
            st.subheader("Disparar Relatório")
            with st.form("form_email"):
                email_dest = st.text_input("E-mail de Destino")
                assunto = st.text_input("Assunto", value="Relatório de Status - TI")
                msg = st.text_area("Mensagem", value="Olá! Segue em anexo o relatório.")
                anexar = st.checkbox("Anexar PDF?", value=True)
                if st.form_submit_button("✉️ Enviar Agora"):
                    if email_dest:
                        sucesso, retorno = enviar_email(email_dest, assunto, msg, gerar_pdf() if anexar else None)
                        if sucesso: st.success(retorno)
                        else: st.error(retorno)

        with tab3:
            st.subheader("Configurar Recorrência Diária")
            horario = st.time_input("Horário do disparo")
            email_auto = st.text_input("E-mail de destino automático:")
            if st.button("Ligar Automação Diária", type="primary"):
                if email_auto:
                    hora_str = horario.strftime("%H:%M")
                    schedule.clear()
                    # Passa as credenciais de quem logou para a tarefa em background
                    schedule.every().day.at(hora_str).do(tarefa_agendada, destinatario=email_auto, remetente=st.session_state['email_usuario'], senha=st.session_state['senha_usuario'])
                    st.success(f"Agendamento Ativado! E-mails sairão de {st.session_state['email_usuario']} todos os dias às {hora_str}.")
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoAlertPresentException,
    UnexpectedAlertPresentException,
    JavascriptException,
)

import time
import csv
import re
import threading

import os
import requests
from urllib.parse import urlparse

import sys

from dotenv import load_dotenv

# ======= CONFIGURAÇÕES =======
# Substitua pelas suas credenciais (recomendo usar variáveis de ambiente em produção)
USUARIO = os.getenv("USUARIO")
SENHA = os.getenv("SENHA")

# URLs e arquivos de saída
URL_LOGIN = "https://perfil.estrategia.com/login?source=legado-polvo&target=https%3A%2F%2Fwww.estrategiaconcursos.com.br%2Faccounts%2Flogin%2F%3F"
BASE_SITE = "https://www.estrategiaconcursos.com.br"
#URL_AULAS = "https://www.estrategiaconcursos.com.br/app/dashboard/cursos/226024/aulas/2079761/videos/250666"
URL_AULAS = "https://www.estrategiaconcursos.com.br/app/dashboard/cursos/226005/aulas"
ARQUIVO_SAIDA = "Direito Administrativo.csv"
PASTA_DESTINO = "videos_baixados"

# Seletores usados no script (centralizados para facilitar manutenção)
SELECTORES = {
    "email": [
        (By.NAME, "loginField"),
        (By.NAME, "login"),
        (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.ID, "email"),
    ],
    "senha": [
        (By.NAME, "passwordField"),
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.ID, "password"),
    ],
    "botao_continuar": [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//button[contains(., 'Continuar')]"),
        (By.XPATH, "//button[contains(., 'Entrar')]")
    ],
    "lista_videos": [
        ".StyledScrollbars.ListVideos-items a.VideoItem",
        ".ListVideos-items a.VideoItem",
        ".VideoItem"
    ],
    "video_player": ".video-react, video",
    "titulo_video": ".VideoItem-info-title",
}

# ======= CONFIGURAÇÃO DO NAVEGADOR =======
def iniciar_driver(headless=False):
    """
    Inicializa o driver do Chrome com opções básicas.
    Em headless, algumas interações manuais podem falhar — usar com cautela.
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")  # modo invisível / cuidado com headless e interação manual
    options.add_argument("--start-maximized")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=options)
    return driver

# ======= FUNÇÕES AUXILIARES =======
def try_accept_alert(driver, short_wait=3):
    """
    Tenta aceitar alertas popup caso existam.
    Retorna True se algum alerta foi aceito.
    """
    try:
        WebDriverWait(driver, short_wait).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        print(f"⚠️ Alerta detectado: {alert.text}")
        alert.accept()
        print("✅ Alerta fechado.")
        return True
    except (TimeoutException, NoAlertPresentException):
        return False
    except UnexpectedAlertPresentException:
        try:
            alert = driver.switch_to.alert
            print(f"⚠️ Alerta (catch): {alert.text}")
            alert.accept()
            return True
        except Exception:
            return False

def find_clickable(driver, locator_list, timeout=20):
    """
    Tenta encontrar o primeiro elemento clicável dentre vários seletores.
    Retorna o elemento ou None se não encontrado.
    """
    deadline = time.time() + timeout
    wait = WebDriverWait(driver, max(2, int(timeout // len(locator_list))))
    for by, sel in locator_list:
        try:
            element = wait.until(EC.element_to_be_clickable((by, sel)))
            return element
        except Exception:
            if time.time() > deadline:
                break
            continue
    return None

def format_seconds_to_hhmmss(sec_float):
    """
    Formata um tempo em segundos para string hh:mm:ss ou mm:ss.
    """
    if sec_float is None:
        return None
    try:
        sec = int(round(float(sec_float)))
    except Exception:
        return None
    hours = sec // 3600
    minutes = (sec % 3600) // 60
    seconds = sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def limpar_popups_ou_overlays(driver):
    """
    Remove pop-ups ou overlays conhecidos (como getsitecontrol, modais, banners, etc.)
    que possam bloquear cliques durante a execução.
    """
    try:
        driver.execute_script("""
            document.querySelectorAll(
                'getsitecontrol-widget, iframe[src*="getsitecontrol"], ' +
                '.gsc-popup, .modal, .overlay, .popup, [id*="newsletter"], [class*="modal"]'
            ).forEach(e => e.remove());
        """)
    except JavascriptException:
        pass
    time.sleep(0.3)

# ======= FUNÇÕES PRINCIPAIS =======
def aguardar_resolucao_manual_captcha(enter_event):
    """
    Função que espera o usuário resolver o CAPTCHA manualmente no navegador.
    O usuário pode clicar no botão 'Continuar' no navegador para avançar,
    ou apertar Enter aqui no terminal para continuar o fluxo.
    """
    input("⚠️ CAPTCHA detectado! Resolva-o manualmente no navegador.\n"
          "Quando terminar, clique em 'Continuar' no navegador ou aperte Enter aqui para continuar...\n")
    enter_event.set()

def realizar_login(driver, usuario, senha):
    """
    Realiza o login no site com o usuário e senha fornecidos.
    Lida com CAPTCHA caso apareça, esperando clique manual no botão 'Continuar' após resolver.
    """
    print("🔐 Iniciando processo de login...")
    driver.get(URL_LOGIN)
    time.sleep(0.5)
    try_accept_alert(driver, short_wait=5)

    # Preencher email
    email_input = find_clickable(driver, SELECTORES["email"], timeout=15)
    if email_input:
        email_input.clear()
        email_input.send_keys(usuario)
        print("✅ Email preenchido.")
    else:
        print("❌ Não encontrei o campo de e-mail automaticamente. Tente preencher manualmente.")
        return False

    # Preencher senha
    senha_input = find_clickable(driver, SELECTORES["senha"], timeout=10)
    if senha_input:
        try:
            senha_input.clear()
            senha_input.send_keys(senha)
            print("🔑 Senha preenchida.")
        except Exception:
            try:
                email_input.send_keys(Keys.TAB)
                time.sleep(0.3)
                driver.switch_to.active_element.send_keys(senha)
                print("🔑 Senha preenchida via TAB.")
            except Exception:
                print("⚠️ Não consegui preencher o campo senha automaticamente.")
                return False
    else:
        print("⚠️ Não localizei o campo de senha automaticamente. Digite manualmente.")
        return False

    # Clicar automaticamente no botão Continuar (primeiro clique)
    continuar_btn = find_clickable(driver, SELECTORES["botao_continuar"], timeout=5)
    if continuar_btn:
        continuar_btn.click()
        print("▶️ Botão 'Continuar' clicado automaticamente.")
    else:
        print("⚠️ Botão 'Continuar' não encontrado. Clique manualmente no navegador.")

        # Tenta localizar o botão "Continuar" na página pelo seletor (ajuste o seletor conforme seu caso)
        while True:
            btn = find_clickable(driver, SELECTORES["botao_continuar"], timeout=2)
            if btn:
                # Verifica se o botão está invisível ou desabilitado
                # Se sim, presumimos que ele foi clicado e a página avançou
                if not btn.is_displayed() or not btn.is_enabled():
                    print("▶️ Botão 'Continuar' foi clicado (não visível/ativado). Avançando...")
                    break
            else:
                # Caso o botão não seja encontrado (por exemplo, desapareceu da página),
                # também consideramos que foi clicado e avançamos
                print("▶️ Botão 'Continuar' desapareceu da página. Avançando...")
                break

            # Aguarda meio segundo antes de tentar novamente para não sobrecarregar o CPU
            time.sleep(0.5)

    # Dá um tempo para a página carregar o CAPTCHA (se houver)
    time.sleep(3)

    # Detectar se captcha apareceu
    captcha_iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
    if captcha_iframes:
        enter_event = threading.Event()
        thread = threading.Thread(target=aguardar_resolucao_manual_captcha, args=(enter_event,), daemon=True)
        thread.start()

        # print("⚠️ CAPTCHA detectado! Resolva-o no navegador.")

        url_antes = driver.current_url

        while True:
            # Verifica se o iframe do reCAPTCHA ainda está na página (captcha não resolvido)
            try_accept_alert(driver, short_wait=5)
            captchas = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
            try_accept_alert(driver, short_wait=5)
            if captchas:
                print("⏳ Aguardando resolução do CAPTCHA...")
                time.sleep(1)
                continue

            # Verifica se a URL mudou (assumindo avanço)
            if driver.current_url != url_antes:
                print("▶️ URL mudou após CAPTCHA, assumindo que avançou.")
                break
            
            # Usado para cobrir o caso em que o CAPTCHA é resolvido mas a URL não muda imediatamente
            # Tenta achar algum botão continuar entre todos os seletores possíveis
            btn = None
            for by, sel in SELECTORES["botao_continuar"]:
                try:
                    candidate = driver.find_element(by, sel)
                    if candidate.is_displayed() and candidate.is_enabled():
                        btn = candidate
                        break
                except:
                    continue

            if btn:
                print("▶️ Botão 'Continuar' reapareceu após CAPTCHA. Por favor, clique nele ou aperte Enter.")
                while True:
                    try:
                        # Recheca se o botão ainda está clicável
                        candidate_check = driver.find_element(by, sel)
                        if not candidate_check.is_displayed() or not candidate_check.is_enabled():
                            print("▶️ Detectado clique no botão 'Continuar' após CAPTCHA.")
                            break
                    except Exception:
                        print("▶️ Botão 'Continuar' sumiu após CAPTCHA (clicado).")
                        break

                    if enter_event.is_set():
                        print("▶️ Enter pressionado no terminal. Continuando fluxo.")
                        break

                    time.sleep(0.3)
                break
            else:
                print("⏳ Botão 'Continuar' não encontrado ainda, aguardando...")
                time.sleep(1)

            if enter_event.is_set():
                print("▶️ Enter pressionado no terminal. Continuando fluxo.")
                break
    else:
        print("✅ Nenhum CAPTCHA detectado, seguindo fluxo...")

    try_accept_alert(driver, short_wait=6)
    return True

def garantir_pagina_aulas(driver):
    """
    Garante que estamos na página das aulas, navegando para ela se necessário.
    """
    try:
        current_url = driver.current_url
    except Exception:
        current_url = ""

    if not current_url.startswith(BASE_SITE) or "aulas" not in current_url:
        print("🔎 Indo para a URL das aulas...")
        driver.get(URL_AULAS)
        try_accept_alert(driver, short_wait=5)
        time.sleep(2)

def coletar_lista_videos(driver):
    """
    Coleta os títulos e elementos dos vídeos da página.
    Retorna lista de tuplas (titulo, elemento).
    """
    print("⏳ Coletando lista de vídeos na página...")
    lista_css = ",".join(SELECTORES["lista_videos"])
    elementos_video = WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, lista_css))
    )
    videos = []
    for el in elementos_video:
        try:
            title_el = el.find_element(By.CSS_SELECTOR, SELECTORES["titulo_video"])
            titulo = title_el.text.strip()
        except Exception:
            titulo = el.text.strip() or "(sem título)"
        videos.append((titulo, el))
    print(f"🎥 {len(videos)} vídeos encontrados.")
    return videos

def extrair_duracao_video(driver, video_el):
    """
    Abre o vídeo clicando no elemento, espera o player carregar, toca o vídeo mudo,
    extrai a duração e volta para a lista.
    Retorna duração formatada (hh:mm:ss) ou mensagem de erro.
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", video_el)
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(video_el)).click()
    except Exception:
        return "ERRO AO ABRIR"

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTORES["video_player"]))
        )
    except TimeoutException:
        driver.back()
        return "SEM PLAYER"

    try:
        # Força o vídeo a tocar mudo para carregar metadadosW
        driver.execute_script("""
            var v=document.querySelector('video');
            if(v){
                v.muted = true;
                v.play().catch(()=>{});
            }
        """)

        # Espera até que a duração esteja disponível
        start_time = time.time()
        duracao = None
        while time.time() - start_time < 30:
            duracao = driver.execute_script("""
                var v=document.querySelector('video');
                if(v && typeof v.duration === 'number' && isFinite(v.duration) && v.duration > 0){
                    return v.duration;
                }
                return null;
            """)
            if duracao:
                break
            time.sleep(0.2)

        driver.back()
        return format_seconds_to_hhmmss(duracao) if duracao else "DURAÇÃO N/D"
    except Exception:
        driver.back()
        return "ERRO AO PEGAR DURAÇÃO"

def fechar_modal_se_existir(driver):
    """
    Fecha o modal 'beamerPushModalContent' se ele estiver presente na tela.
    """
    try:
        modal = WebDriverWait(driver, 2).until(
            EC.presence_of_element_located((By.ID, "beamerPushModalContent"))
        )
        fechar_btn = modal.find_element(By.TAG_NAME, "button")
        driver.execute_script("arguments[0].click();", fechar_btn)
        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located((By.ID, "beamerPushModalContent"))
        )
        print("ℹ️ Modal fechado com sucesso.")
    except:
        pass  # Modal não estava aberto

def clicar_elemento_com_rolagem(driver, elemento, espera_clicavel=True, sleep_apos=1, ajuste_rolagem=-100):
    """
    Rola a página para o elemento, ajusta para evitar sobreposição,
    espera até o elemento estar clicável (opcional),
    e tenta clicar no elemento (com fallback para JS click).
    Por fim, espera o tempo sleep_apos.
    """
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
    driver.execute_script(f"window.scrollBy(0, {ajuste_rolagem});")  # Ajusta rolagem vertical
    time.sleep(0.5)

    if espera_clicavel:
        try:
            WebDriverWait(driver, 5).until(
                lambda d: elemento.is_displayed() and elemento.is_enabled()
            )
        except TimeoutException:
            href = elemento.get_attribute("href") if elemento else "unknown"
            print(f"⚠️ Timeout esperando elemento clicável: {href}")

    try:
        elemento.click()
    except Exception:
        driver.execute_script("arguments[0].click();", elemento)

    time.sleep(sleep_apos)

# ========= FUNÇÕES NOVAS PARA EVITAR REPETIÇÃO =========
def obter_titulo_e_subtitulo(aula):
    """
    Extrai título e subtítulo da aula (com fallback para evitar erro).
    """
    try:
        titulo = aula.find_element(By.CSS_SELECTOR, "h2.SectionTitle").text.strip()
    except:
        titulo = "(Sem título)"
    try:
        subtitulo = aula.find_element(By.CSS_SELECTOR, "p.sc-gZMcBi").text.strip()
    except:
        subtitulo = ""
    return titulo, subtitulo

def processar_aula(driver, aula, callback_video):
    """
    Processa uma aula expandindo, coletando os vídeos e executando um callback em cada vídeo.
    O callback recebe (idx, titulo_video, elemento_video, titulo_aula, subtitulo_aula, total_videos).
    """
    titulo_aula, subtitulo_aula = obter_titulo_e_subtitulo(aula)
    print(f"📖 {titulo_aula}")
    print(f"📝 {subtitulo_aula}")

    # Fecha modal se aparecer
    fechar_modal_se_existir(driver)

    # Expande a aba da aula
    clicar_elemento_com_rolagem(driver, aula, espera_clicavel=True, sleep_apos=1, ajuste_rolagem=-100)

    # maximo = 0
    # # Coleta vídeos da aula
    # videoaulas = coletar_lista_videos(driver)
    # for idx, (titulo, video_el) in enumerate(videoaulas, start=1):
    #     callback_video(idx, titulo, video_el, titulo_aula, subtitulo_aula, len(videoaulas))
    #     if maximo >= 2:
    #         break
    #     maximo += 1
    
    # Coleta vídeos da aula
    videoaulas = coletar_lista_videos(driver)
    for idx, (titulo, video_el) in enumerate(videoaulas, start=1):
        callback_video(idx, titulo, video_el, titulo_aula, subtitulo_aula, len(videoaulas))

    # Fecha a aba após processar
    clicar_elemento_com_rolagem(driver, aula, espera_clicavel=False, sleep_apos=0.5, ajuste_rolagem=-100)

def coletar_aulas_e_videoaulas(driver):
    """
    Coleta todas as aulas (abas) e suas videoaulas com duração.
    Retorna lista de tuplas: (titulo_aula, subtitulo_aula, numero_video, titulo_video, duracao).
    """
    resultado = []
    elementos_aulas = driver.find_elements(By.CSS_SELECTOR, "a.Collapse-header")

    def callback(idx, titulo, video_el, titulo_aula, subtitulo_aula, total_videos):
        duracao = extrair_duracao_video(driver, video_el)
        print(f"   🕒 Vídeo {idx}/{total_videos}: {titulo} - {duracao}")
        resultado.append((titulo_aula, subtitulo_aula, idx, titulo, duracao))

    # maximo = 0
    # for aula in elementos_aulas:
    #     processar_aula(driver, aula, callback)
    #     if maximo >= 2:
    #         break
    #     maximo += 1
    
    for aula in elementos_aulas:
        processar_aula(driver, aula, callback)

    return resultado

def salvar_em_csv(nome_arquivo, dados, header=None):
    """
    Salva a lista dos dados fornecidos em um arquivo CSV.
    Se quiser salvar na lista os nomes das colunas para o cabeçalho do CSV, remova o valor None de header.
    """
    with open(nome_arquivo, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        if header:
            writer.writerow(header)
        for linha in dados:
            writer.writerow(linha)
    print(f"✅ Dados salvos no arquivo {nome_arquivo}")

def construir_nome_arquivo(titulo_aula, subtitulo_aula, idx, titulo_video, url, resolucao):
    """
    Gera um nome de arquivo limpo com base no título da aula e do vídeo.
    """
    base = f"{titulo_aula} - {subtitulo_aula} - Vídeo {idx:02d} - {titulo_video} ({resolucao})"
    base = re.sub(r'[\\/*?:"<>|]', "", base)  # remove caracteres inválidos
    base = base.strip().replace("  ", " ")
    ext = os.path.splitext(urlparse(url).path)[1]
    return base + ext

def extrair_resolucao(url):
    """
    Extrai a resolução de uma URL de vídeo que contém em seu conteúdo descrito a resolução
    """
    # Usa expressão regular para procurar padrões do tipo '360p', '480p', '720p', '1080p', etc.
    # \d{3,4} → procura 3 ou 4 dígitos (ex: 360, 720, 1080)
    # p       → seguido da letra 'p'
    padrao = re.search(r'(\d{3,4}p)', url)  # procura algo como "720p", "1080p"
    if padrao:
        return padrao.group(1)
    return None

def obter_link_download_maior_resolucao(driver):
    """
    Aguarda e retorna o link da maior resolução disponível (prioridade: 720p > 480p > 360p).
    """
    try:
        # Clica na seção "Opções de download" para expandir os links
        download_section = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//strong[contains(text(), 'Opções de download')]"))
        )
        
        # Verifica se a div com os links já está presente
        links_container = driver.find_elements(By.CSS_SELECTOR, "div.sc-Rmtcm.cKiCd")

        if not links_container:  
            # Só clica se os links ainda não estiverem disponíveis
            download_section.click()
            time.sleep(1) # Dá tempo para o DOM expandir e os links aparecerem

            # Aguarda os links aparecerem
            links_container = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.sc-Rmtcm.cKiCd"))
            )

        # Agora coleta os links
        links = driver.find_elements(By.CSS_SELECTOR, "div.sc-Rmtcm.cKiCd a.Button.-small")
        links_info = [(link.text.strip().lower(), link.get_attribute("href")) for link in links if link.get_attribute("href")]

        # Define a ordem de prioridade das resoluções
        resolucoes_prioridade = ["720p", "480p", "360p"]
        #resolucoes_prioridade = ["1080p"]

        # Tenta pegar o primeiro link disponível de acordo com a prioridade
        for resolucao in resolucoes_prioridade:
            for link in links:
                href = link.get_attribute("href")
                if href and resolucao in link.text.strip().lower():
                    print(f"🎯 Link encontrado com resolução/prioridade {resolucao}")
                    return resolucao, href  # retorna a resolução e o href
    
        # Se não encontrar nenhum link com as resoluções prioritárias, retorna o primeiro link válido
        if links_info:
            #primeira_resolucao, primeiro_href = links_info[0]
            primeiro_href = links_info[0][1]
            primeira_resolucao = extrair_resolucao(primeiro_href)
            print(f"⚠️ Nenhum link nas resoluções preferidas. Usando: {primeira_resolucao}, que é o primeiro link válido.")
            return primeira_resolucao, primeiro_href  # fallback

        print("❌ Nenhum link disponível.")
        return None, None
    
    except TimeoutException as e:
        print(f"⚠️ Erro ao obter link de download: {e}")

    return None, None

def baixar_arquivo(url, caminho_arquivo):
    """
    Faz o download via requests, com contagem progressiva de porcentagem.
    """
    try:
        resposta = requests.get(url, stream=True, timeout=60)
        resposta.raise_for_status()
        
        tamanho_total_bytes = int(resposta.headers.get('content-length', 0))
        tamanho_bloco = 1024 * 1024  # 1MB
        total_bytes_baixados = 0
        tempo_inicio = time.time()

        # Faz o download do arquivo, iterando em blocos (bloco) de até 1MB cada (tamanho_bloco)
        with open(caminho_arquivo, "wb") as arquivo:
            for bloco in resposta.iter_content(chunk_size=tamanho_bloco):
                if bloco:
                    arquivo.write(bloco)
                    total_bytes_baixados += len(bloco)
                    porcentagem = (total_bytes_baixados / tamanho_total_bytes) * 100 if tamanho_total_bytes else 0

                    # Tempo decorrido e velocidade média
                    tempo_decorrido = time.time() - tempo_inicio
                    minutos = int(tempo_decorrido // 60)
                    segundos = int(tempo_decorrido % 60)
                    tempo_formatado = f"{minutos:02d}:{segundos:02d}"
                    velocidade_media = (total_bytes_baixados / 1024 / 1024) / tempo_decorrido if tempo_decorrido > 0 else 0

                    # Atualiza a linha com o progresso
                    sys.stdout.write(
                        f"\r⬇️ Download: {porcentagem:.2f}% "
                        f"({total_bytes_baixados // (1024 * 1024)} MB de {tamanho_total_bytes // (1024 * 1024)} MB) "
                        f"[{tempo_formatado}, {velocidade_media:.2f}MB/s]"
                    )
                    sys.stdout.flush()

        print(f"\n✅ Download concluído: {os.path.basename(caminho_arquivo)}")
        
    except Exception as e:
        print(f"❌ Erro ao baixar: {e}")

def realizar_downloads(driver):
    """
    Percorre todas as aulas e baixa os vídeos na maior resolução disponível (preferencialmente 720p).
    Retorna uma lista de vídeos processados para permitir contagem fora da função.
    """
    print("📥 Iniciando processo de download das videoaulas...")
    
    os.makedirs(PASTA_DESTINO, exist_ok=True)
    elementos_aulas = driver.find_elements(By.CSS_SELECTOR, "a.Collapse-header")

    resultados = []  # lista para acumular vídeos processados

    def callback(idx, titulo, video_el, titulo_aula, subtitulo_aula, total_videos):
        # salva info do vídeo processado
        resultados.append((titulo_aula, subtitulo_aula, idx, titulo))

        print(f"▶️ {idx}/{total_videos} - {titulo}")
        clicar_elemento_com_rolagem(driver, video_el, espera_clicavel=True)

        # Remove pop-ups ou overlays conhecidos (Neste caso, remover o pop-up de aceitação de cookies)
        limpar_popups_ou_overlays(driver)
        
        resolucao, url = obter_link_download_maior_resolucao(driver)
        if url:
            nome_arquivo = construir_nome_arquivo(titulo_aula, subtitulo_aula, idx, titulo, url, resolucao)
            caminho = os.path.join(PASTA_DESTINO, nome_arquivo)

            if os.path.exists(caminho):
                print(f"✔️ Já existe: {nome_arquivo}")
            else:
                print(f"⬇️ Baixando: {nome_arquivo}")
                baixar_arquivo(url, caminho)
        else:
            print("❌ Nenhum link de vídeo encontrado.")

        driver.back()

    for aula in elementos_aulas:
        processar_aula(driver, aula, callback)

    return resultados

# ======= FLUXO PRINCIPAL =======
def main():
    print("🧠 Escolha o que deseja fazer:")
    print("1 - Extrair duração das videoaulas")
    print("2 - Baixar todas as videoaulas (resolução mais alta disponível)")

    escolha = input("Digite 1 ou 2: ").strip()
    if escolha not in ["1", "2"]:
        print("❌ Opção inválida. Encerrando.")
        return

    driver = iniciar_driver(headless=False)

    try:
        sucesso_login = realizar_login(driver, USUARIO, SENHA)
        if not sucesso_login:
            print("❌ Falha no login. Encerrando.")
            return

        garantir_pagina_aulas(driver)
        time.sleep(3)

        if escolha == "1":
            # -------------------- OPÇÃO 1: DURAÇÃO ------------------------
            # Coleta a estrutura hierárquica: aulas e videoaulas com durações
            aulas_e_videoaulas = coletar_aulas_e_videoaulas(driver)

            total_videos = len(aulas_e_videoaulas)
            print(f"🎥 {total_videos} vídeos encontrados no total.")

            salvar_em_csv(ARQUIVO_SAIDA, aulas_e_videoaulas, header=["Aula", "Subtítulo", "Vídeo", "Videoaula", "Duração"])

        elif escolha == "2":
            # -------------------- OPÇÃO 2: DOWNLOAD ------------------------
            # Realiza o download das videoaulas de acordo com a estrutura hierárquica: aulas e videoaulas
            videos_baixados = realizar_downloads(driver)

            total_videos = len(videos_baixados)
            print(f"🎥 {total_videos} vídeos processados no total.")

    finally:
        driver.quit()
        print("🔚 Processo finalizado.")


if __name__ == "__main__":
    main()

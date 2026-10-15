"""
Caçador de voos baratos — Google Flights (aba Explorar, via SerpApi) → WhatsApp (CallMeBot).

Uso:
  python buscar_voos.py                 busca e envia no WhatsApp
  python buscar_voos.py --seco          busca e só mostra na tela (não envia, não grava histórico)
  python buscar_voos.py --teste-whatsapp  manda uma mensagem de teste
"""
import json
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent
CONFIG = PASTA / "config.json"
HISTORICO = PASTA / "historico_enviados.json"
ESTADO = PASTA / "estado_rodizio.json"
LOG = PASTA / "log.txt"


def log(msg):
    linha = f"[{datetime.now():%Y-%m-%d %H:%M}] {msg}"
    print(linha)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linha + "\n")


def carregar_json(caminho, padrao):
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return padrao


def http_get(url, params, timeout=60):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "cacador-voos/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


MUNDO = "/m/02j71"  # "qualquer lugar" no Google Flights


def normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


EUROPA = "/m/02j9z"


def buscar_area(cfg, area_id, ida, volta, teto, mes=None, duracao=2):
    # com `mes`, o Google escolhe as datas mais baratas do mês (só aceita até 6 meses à frente)
    datas = ({"month": mes, "travel_duration": duracao} if mes
             else {"type": 1, "outbound_date": ida, "return_date": volta})
    params = {
        "engine": "google_travel_explore",
        "api_key": cfg["serpapi_key"],
        "departure_id": cfg["origens"],
        "arrival_area_id": area_id,
        **datas,
        "currency": "BRL",
        "gl": "br",
        "hl": "pt-BR",
        "travel_mode": 1,  # só voo
        "max_price": teto,
    }
    dados = json.loads(http_get("https://serpapi.com/search.json", params))
    if "error" in dados:
        raise RuntimeError(dados["error"])
    return dados.get("destinations", [])


def link_google_flights(destino, ida, volta, origens):
    if destino.get("link"):
        return destino["link"]
    aeroporto = destino.get("destination_airport", {})
    codigo = aeroporto.get("code") if isinstance(aeroporto, dict) else aeroporto
    alvo = codigo or destino.get("name", "")
    q = f"Flights to {alvo} from {origens} on {ida} through {volta}"
    return "https://www.google.com/travel/flights?" + urllib.parse.urlencode(
        {"q": q, "curr": "BRL", "hl": "pt-BR", "gl": "br"}
    )


def dias_entre(ida, volta):
    return (date.fromisoformat(volta) - date.fromisoformat(ida)).days


def fmt_brl(v):
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def fmt_data(iso):
    d = date.fromisoformat(iso)
    return f"{d.day:02d}/{d.month:02d}"


def meses_europa(eu, hoje):
    """Meses de 2027 liberados (a partir de março) que já estão dentro dos 6 meses do Google."""
    meses = []
    for i in range(6):
        a, m = divmod(hoje.month - 1 + i, 12)
        ano_mes = f"{hoje.year + a}-{m + 1:02d}"
        if eu["de"][:7] <= ano_mes <= eu["ate"][:7]:
            meses.append(ano_mes)
    return meses


TIPO_IMOVEL = {"apartment": "Apartamento", "home": "Casa", "house": "Casa", "loft": "Loft",
               "condo": "Apartamento", "guesthouse": "Casa de hóspedes", "guest suite": "Suíte independente",
               "townhouse": "Sobrado", "cottage": "Chalé", "cabin": "Cabana", "villa": "Vila",
               "bungalow": "Bangalô", "tiny home": "Casinha"}


def buscar_airbnb(cfg, cidade, pais, check_in, check_out):
    """Imóvel inteiro (nunca quarto na casa de alguém) com banheiro e cozinha; estúdio vale."""
    ab = cfg["airbnb"]
    params = {
        "engine": "airbnb",
        "api_key": cfg["serpapi_key"],
        "q": f"{cidade}, {pais}",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "currency": "BRL",
        "adults": ab["hospedes"],
        # no Airbnb, quarto de hotel e quarto na casa de alguém vêm iguais ("Room in ..."),
        # por isso aqui é só imóvel inteiro e hotel vem do Google Hotels
        "room_type": "entire_home",
        "property_types": ab["tipos"],
        "bathrooms": ab["banheiros_min"],
        "amenities": ab["comodidades"],
    }
    if ab["quartos_min"]:
        params["bedrooms"] = ab["quartos_min"]
    dados = json.loads(http_get("https://serpapi.com/search.json", params, timeout=90))
    if "error" in dados:
        if "hasn't returned any results" in dados["error"]:
            return []
        raise RuntimeError(dados["error"])
    achados = []
    for r in dados.get("organic_results", []):
        preco = r.get("extracted_price")
        if not preco:
            continue
        tipo_en = (r.get("title") or "").split(" in ")[0].strip().lower()
        if "room" in tipo_en or "hotel" in tipo_en:
            continue
        detalhes = [d.lower() for d in r.get("details") or []]
        if any("shared" in d for d in detalhes):
            continue
        detalhes_pt = []
        if any("studio" in d for d in detalhes):
            detalhes_pt.append("estúdio")
        elif r.get("bedrooms"):
            detalhes_pt.append(f"{r['bedrooms']} quarto(s)")
        if r.get("bathrooms"):
            detalhes_pt.append(f"{r['bathrooms']:g} banheiro(s)")
        detalhes_pt.append("cozinha")
        achados.append({
            "preco": preco, "origem": "Airbnb",
            "tipo": TIPO_IMOVEL.get(tipo_en, tipo_en.capitalize() or "Imóvel"),
            "detalhes": detalhes_pt, "nota": r.get("rating"), "avaliacoes": r.get("reviews"),
            "link": (r.get("link") or "").replace("www.airbnb.com/", "www.airbnb.com.br/"),
        })
    return achados


def buscar_hoteis(cfg, cidade, pais, check_in, check_out):
    """Hotel (quarto privativo) pelo Google Hotels; hostel fora, porque o preço é de cama em quarto coletivo."""
    ab, ht = cfg["airbnb"], cfg["hoteis"]
    params = {
        "engine": "google_hotels",
        "api_key": cfg["serpapi_key"],
        "q": f"{cidade}, {pais}",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "currency": "BRL",
        "gl": "br",
        "hl": "pt-BR",
        "adults": ab["hospedes"],
        "sort_by": 3,  # menor preço
        "hotel_class": ",".join(str(e) for e in range(ht["estrelas_min"], 6)),
    }
    dados = json.loads(http_get("https://serpapi.com/search.json", params, timeout=90))
    if "error" in dados:
        if "hasn't returned any results" in dados["error"]:
            return []
        raise RuntimeError(dados["error"])
    achados = []
    for h in dados.get("properties", []):
        preco = (h.get("total_rate") or {}).get("extracted_lowest")
        nome = h.get("name") or "?"
        if not preco or h.get("type") != "hotel":
            continue
        # olha também o site: "Aji" é hostel, só o endereço (ajihostel.com) entrega
        if any(p in normalizar(nome + " " + (h.get("link") or "")) for p in ht["excluir_nomes"]):
            continue
        estrelas = h.get("extracted_hotel_class")
        busca = urllib.parse.urlencode({"q": f"{nome} {cidade}", "hl": "pt-BR", "curr": "BRL"})
        achados.append({
            "preco": preco, "origem": "Hotel", "tipo": nome,
            "detalhes": [f"{estrelas} estrelas"] if estrelas else [],
            "nota": h.get("overall_rating"), "avaliacoes": h.get("reviews"),
            "link": "https://www.google.com/travel/search?" + busca,
        })
    return achados


def mensagens_hospedagem(o, achados):
    """Uma opção por mensagem: as 3 juntas passam de 700 caracteres e o CallMeBot corta."""
    noites = o["dias"]
    titulo = f"🏠 *Hospedagem em {o['cidade']}*"
    cabecalho = (f"{titulo} — {fmt_data(o['ida'])} → {fmt_data(o['volta'])}, {noites} noite(s)\n"
                 f"Airbnb inteiro ou hotel · as {len(achados)} mais baratas\n\n")
    mensagens = []
    for i, a in enumerate(achados, 1):
        detalhes = list(a["detalhes"])
        if a["nota"]:
            detalhes.append(f"⭐ {a['nota']}" + (f" ({a['avaliacoes']})" if a["avaliacoes"] else ""))
        icone = "🏨" if a["origem"] == "Hotel" else "🏡"
        mensagens.append(
            (cabecalho if i == 1 else titulo + "\n") +
            f"{i}. 💰 {fmt_brl(a['preco'])} a estadia toda (~{fmt_brl(a['preco'] / noites)}/noite)\n"
            f"{icone} {a['origem']}: {a['tipo']}{' · ' + ' · '.join(detalhes) if detalhes else ''}\n"
            f"🔗 {a['link']}"
        )
    return mensagens


def enviar_whatsapp(cfg, texto):
    resp = http_get(
        "https://api.callmebot.com/whatsapp.php",
        {"phone": cfg["whatsapp_numero"], "text": texto, "apikey": cfg["callmebot_key"]},
    )
    if "ERROR" in resp.upper() and "QUEUED" not in resp.upper():
        raise RuntimeError(resp[:300])


def main():
    cfg = carregar_json(CONFIG, None)
    # sem chave do CallMeBot ainda, roda como --seco: mostra na tela e não grava histórico
    seco = "--seco" in sys.argv or not str(cfg["callmebot_key"]).isdigit()

    if "--teste-whatsapp" in sys.argv:
        enviar_whatsapp(cfg, "✈️ Teste do caçador de voos: WhatsApp funcionando!")
        log("Mensagem de teste enviada.")
        return

    hoje = date.today()
    eu = cfg["europa_2027"]
    fim_de_ano = hoje <= date.fromisoformat(cfg["buscar_ate"])
    eu_ativo = hoje <= date.fromisoformat(eu["buscar_ate"])
    if not fim_de_ano and not eu_ativo:
        log("Janela de busca encerrada; nada a fazer.")
        return

    historico = carregar_json(HISTORICO, {})
    regiao_do_pais = {normalizar(p): r for r in cfg["regioes"] for p in r["paises"]}
    brasil = cfg["brasil_norte_nordeste"]
    cidades_nn = {normalizar(c) for c in brasil["cidades"]}
    br_ignoradas = set()
    teto_geral = max(r["limite"] for r in cfg["regioes"])
    queda_min = cfg["reavisar_se_cair_percentual"] / 100
    ofertas = []
    nao_classificados = set()
    consultas = erros = 0

    # rodízio: cada rodada faz 1 busca "mundo" e 1 busca regional, continuando de onde parou
    estado = carregar_json(ESTADO, {"rodada": 0, "mes": "", "buscas_no_mes": 0})
    mes_atual = f"{date.today():%Y-%m}"
    if estado["mes"] != mes_atual:
        estado["mes"], estado["buscas_no_mes"] = mes_atual, 0
    pares = cfg["pares_de_datas"]
    areas = cfg["buscas_regionais"]
    n = estado["rodada"]
    ida_m, volta_m = pares[n % len(pares)]
    area = areas[n % len(areas)]
    ida_r, volta_r = pares[(n // len(areas)) % len(pares)]
    fila = []
    if fim_de_ano:
        fila += [
            ("Mundo", MUNDO, ida_m, volta_m, teto_geral, None),
            (area["nome"], area["id"], ida_r, volta_r, area["limite"], None),
        ]
        if n % brasil["a_cada_rodadas"] == 0:  # 1x por dia
            ida_b, volta_b = pares[(n // brasil["a_cada_rodadas"]) % len(pares)]
            fila.append(("Brasil", brasil["id"], ida_b, volta_b, brasil["limite"], None))
    # Europa 2027: 1x por dia enquanto roda o fim de ano; depois, toda rodada
    meses_eu = meses_europa(eu, hoje) if eu_ativo else []
    if meses_eu and (not fim_de_ano or n % eu["a_cada_rodadas"] == 1):
        k = estado.get("rodada_eu", 0)
        ano_mes = meses_eu[k % len(meses_eu)]
        fila.append((eu["nome"], EUROPA, max(eu["de"], hoje.isoformat()), eu["ate"], eu["limite"], ano_mes))
        if "--seco" not in sys.argv:
            estado["rodada_eu"] = k + 1
    if "--seco" not in sys.argv:
        estado["rodada"] = n + 1

    for nome_busca, area_id, ida, volta, teto, ano_mes in fila:
        if estado["buscas_no_mes"] >= cfg["limite_buscas_mes"]:
            log(f"Trava: {estado['buscas_no_mes']} buscas este mês; pausado até virar o mês.")
            break
        dias = dias_entre(ida, volta)
        fator = cfg["fator_viagem_longa"] if dias >= cfg["viagem_longa_a_partir_de_dias"] else 1
        rotulo = f"{nome_busca} {ano_mes or ida + '->' + volta}"
        try:
            estado["buscas_no_mes"] += 1
            destinos = buscar_area(cfg, area_id, ida, volta, teto,
                                   mes=int(ano_mes[5:]) if ano_mes else None, duracao=eu["duracao"])
            consultas += 1
            log(f"{rotulo}: {len(destinos)} destinos devolvidos pelo Google")
        except Exception as e:
            erros += 1
            log(f"ERRO {rotulo}: {e}")
            continue

        for d in destinos:
            preco = d.get("flight_price")
            pais = (d.get("country") or "").strip()
            if ano_mes:  # busca Europa 2027: só países da Europa, teto fixo (sem regra de viagem longa)
                if regiao_do_pais.get(normalizar(pais), {}).get("nome") != "Europa":
                    continue
                regiao = eu | {"sem_regra_viagem_longa": True}
            elif normalizar(pais) == "brasil":  # só Norte/Nordeste, reconhecidos pela cidade
                regiao = brasil if normalizar(d.get("name")) in cidades_nn else None
                if regiao is None:
                    br_ignoradas.add(d.get("name") or "?")
                    continue
            else:
                regiao = regiao_do_pais.get(normalizar(pais))
            if regiao is None:  # América do Norte, África, Oceania ou país fora da lista
                nao_classificados.add(pais)
                continue
            limite = regiao["limite"] if regiao.get("sem_regra_viagem_longa") else round(regiao["limite"] * fator)
            if not preco or preco > limite:
                continue
            inicio = d.get("start_date") or ("" if ano_mes else ida)
            fim = d.get("end_date") or ("" if ano_mes else volta)
            if not inicio or not fim:
                continue
            if inicio < ida or fim > volta:  # ida e volta sempre dentro da janela
                continue
            chave = f"{d.get('name')}|{pais}|{inicio}|{fim}"
            anterior = historico.get(chave)
            if anterior and preco > anterior * (1 - queda_min):
                continue  # já avisado e não caiu o suficiente
            ofertas.append({
                "chave": chave, "regiao": regiao["nome"], "cidade": d.get("name", "?"),
                "pais": pais, "preco": preco, "ida": inicio, "volta": fim,
                "dias": dias_entre(inicio, fim), "paradas": d.get("number_of_stops"),
                "cia": d.get("airline") or "", "caiu_de": anterior,
                "link": link_google_flights(d, inicio, fim, cfg["origens"]),
            })
        time.sleep(1)

    ESTADO.write_text(json.dumps(estado, indent=1), encoding="utf-8")
    if br_ignoradas:
        log("Cidades do Brasil ignoradas (não estão na lista Norte/Nordeste): " + ", ".join(sorted(br_ignoradas)))
    if nao_classificados:
        log("Ignorados (fora das regiões ou não estão na lista): " + ", ".join(sorted(nao_classificados)))

    # mesma cidade/datas pode aparecer em mais de uma consulta: fica a mais barata
    melhores = {}
    for o in ofertas:
        if o["chave"] not in melhores or o["preco"] < melhores[o["chave"]]["preco"]:
            melhores[o["chave"]] = o
    ofertas = list(melhores.values())

    log(f"{consultas} consultas, {erros} erros, {len(ofertas)} ofertas novas.")
    if not ofertas:
        return

    # na mensagem, uma linha por cidade: a data mais barata, avisando se há outras
    por_cidade = {}
    for o in sorted(ofertas, key=lambda o: o["preco"]):
        por_cidade.setdefault((o["cidade"], o["pais"]), []).append(o)
    destaque = sorted((v[0] | {"outras": len(v) - 1} for v in por_cidade.values()),
                      key=lambda o: (o["regiao"], o["preco"]))

    blocos = []
    for o in destaque:
        escalas = "direto" if o["paradas"] == 0 else f"{o['paradas']} escala(s)" if o["paradas"] else ""
        extra = f" (antes {fmt_brl(o['caiu_de'])})" if o["caiu_de"] else ""
        blocos.append(
            f"✈️ *{o['cidade']}, {o['pais']}* ({o['regiao']})\n"
            f"💰 {fmt_brl(o['preco'])}{extra} ida e volta\n"
            f"📅 {fmt_data(o['ida'])} → {fmt_data(o['volta'])} ({o['dias']} dias)"
            f"{' · ' + o['cia'] if o['cia'] else ''}{' · ' + escalas if escalas else ''}\n"
            f"{'➕ mais ' + str(o['outras']) + ' opção(ões) de data no limite' + chr(10) if o['outras'] else ''}"
            f"🔗 {o['link']}"
        )

    # CallMeBot corta mensagem longa sem avisar (13/10: 4 cidades juntas, só 2 chegaram);
    # por isso uma cidade por mensagem, e o Airbnb dela vai numa mensagem logo depois
    for i in range(len(blocos)):
        cabecalho = "🔥 *Voos baratos!*\n\n" if i == 0 else ""
        mensagens = [cabecalho + blocos[i]]
        o = destaque[i]
        buscas = []
        if cfg.get("airbnb", {}).get("ativo"):
            buscas.append(("Airbnb", buscar_airbnb))
        if cfg.get("hoteis", {}).get("ativo"):
            buscas.append(("Hotéis", buscar_hoteis))
        opcoes = []
        for nome_busca, buscar in buscas:
            if estado["buscas_no_mes"] >= cfg["limite_buscas_mes"]:
                log(f"{nome_busca} {o['cidade']}: pulado, trava de {cfg['limite_buscas_mes']} buscas no mês.")
                continue
            try:
                estado["buscas_no_mes"] += 1
                achados = buscar(cfg, o["cidade"], o["pais"], o["ida"], o["volta"])
                log(f"{nome_busca} {o['cidade']} {o['ida']}->{o['volta']}: {len(achados)} opções")
                opcoes += achados
            except Exception as e:
                log(f"ERRO {nome_busca} {o['cidade']}: {e}")
            ESTADO.write_text(json.dumps(estado, indent=1), encoding="utf-8")
        if opcoes:
            opcoes.sort(key=lambda a: a["preco"])
            mensagens += mensagens_hospedagem(o, opcoes[:cfg["airbnb"]["quantos"]])
        for texto in mensagens:
            if seco:
                print("\n" + texto + "\n" + "-" * 40)
            else:
                enviar_whatsapp(cfg, texto)
                time.sleep(3)

    if not seco:
        for o in ofertas:
            historico[o["chave"]] = o["preco"]
        HISTORICO.write_text(json.dumps(historico, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"{len(destaque)} cidades ({len(ofertas)} ofertas) enviadas no WhatsApp.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FALHA GERAL: {e}")
        raise

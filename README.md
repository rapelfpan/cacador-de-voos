# ✈️ Caçador de voos baratos

Um robô que procura passagens baratas no Google Flights três vezes por dia e me avisa no WhatsApp quando aparece uma oferta abaixo do teto que eu defini para cada região. Junto com o voo, ele já manda as hospedagens mais baratas no destino (Airbnb inteiro ou hotel).

## O problema

Eu queria viajar no fim de ano e na Europa em 2027, mas não tinha um destino fixo. Ficar abrindo o Google Flights todo dia e testando combinações de cidades e datas toma muito tempo. Os alertas de preço comuns também não resolvem, porque só acompanham **um trecho específico**, e eu queria saber "qualquer lugar da América do Sul abaixo de R$ 1.800".

## O que ele faz

- Usa a aba **Explorar** do Google Flights para buscar **regiões inteiras** (mundo, América do Sul, Caribe, Europa, Norte/Nordeste do Brasil), saindo de vários aeroportos ao mesmo tempo (GIG, SDU, GRU, VCP, CGH)
- Classifica cada destino pelo país e aplica o **teto de preço da região**
- Em viagens longas (8 dias ou mais), fica mais exigente com o preço (fator configurável)
- **Não repete aviso:** só avisa de novo a mesma oferta se o preço cair pelo menos 5%
- Para cada cidade encontrada, busca as **3 hospedagens mais baratas**. Fica só com imóvel inteiro ou hotel de 3 estrelas ou mais, e descarta hostel e quarto compartilhado.
- Manda **uma mensagem por cidade** no WhatsApp, porque o CallMeBot corta textos longos sem avisar
- **Controla o próprio gasto:** reveza as buscas entre rodadas e para sozinho ao chegar no limite mensal da API gratuita

Exemplo de mensagem:

```
🔥 Voos baratos!

✈️ Montevidéu, Uruguai (América do Sul)
💰 R$ 1.146 ida e volta
📅 21/12 → 31/12 (10 dias) · 1 escala(s)
🔗 https://www.google.com/travel/flights?...
```

## Tecnologias

- **Python 3**, só com a biblioteca padrão (nenhuma dependência para instalar)
- **[SerpApi](https://serpapi.com)**: Google Flights Explore, Google Hotels e Airbnb (plano gratuito)
- **[CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/)**: envio de mensagens no WhatsApp (gratuito)
- **Agendador de Tarefas do Windows** para rodar às 10h, 14h e 17h40

## Como usar

1. Copie `config.exemplo.json` para `config.json` e preencha:
   - `serpapi_key`: sua chave da SerpApi
   - `whatsapp_numero` e `callmebot_key`: siga o passo a passo do CallMeBot
2. Ajuste regiões, tetos de preço e datas no próprio `config.json`
3. Teste sem enviar nada:
   ```
   python buscar_voos.py --seco
   ```
4. Teste o WhatsApp:
   ```
   python buscar_voos.py --teste-whatsapp
   ```
5. Agende para rodar sozinho (PowerShell):
   ```
   .\instalar_agendamento.ps1
   ```

Enquanto a chave do CallMeBot não for preenchida, o robô roda em modo `--seco`: mostra as ofertas na tela e não envia nada.

> 🔒 O `config.json` real fica fora do repositório (está no `.gitignore`) porque guarda chaves e telefone. Só o modelo com valores de exemplo é publicado.

## O que aprendi

- Ler a documentação de uma API e lidar com os limites dela: o Google só aceita busca por mês até 6 meses à frente, e o plano gratuito tem cota mensal
- Tratar dados inconsistentes: o mesmo país aparece com nomes diferentes ("Tchéquia" e "República Tcheca"), e no Airbnb quarto de hotel vem igual a quarto na casa de alguém
- Investigar falhas silenciosas: mensagens que "sumiam" eram cortadas pelo CallMeBot por tamanho

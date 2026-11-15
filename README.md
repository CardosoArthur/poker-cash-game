# Poker Cash Game — treino pessoal

Texas Hold'em **No-Limit** em formato **cash game**, contra bots, no terminal ou no navegador.
Feito em Python 3 (3.9 ou mais novo) usando **só a biblioteca padrão**: não há nada para instalar.

## Como executar

```bash
python main.py          # menu no terminal
python main.py --web    # interface no navegador (http://127.0.0.1:8765)
python -m unittest      # testes
```

### Menu

1. **Nova partida (cash game)**: antes de cada partida você escolhe big blind, small blind,
   fichas iniciais, número de bots (1 a 8), ante, straddle, dificuldade dos bots e se quer o treinador.
2. **Continuar mesa salva**: volta para uma mesa pausada, com os mesmos bots, stacks e botão.
3. **Cenários de prática**: 5 situações fixas (flush draw, decisão no river, side pots,
   trinca em board perigoso, defesa do big blind), cada uma com uma análise no final.
4. **Quiz pré-flop**: decida entre abrir ou desistir com uma mão numa posição; a resposta é corrigida pelo range da posição.
5. **Tabelas de mãos iniciais**: grade 13×13 com o range de abertura de cada posição.
6. **Estatísticas e evolução**: VPIP, PFR, 3-bet, WTSD, W$SD, AF e bb/100 (no total e por posição),
   gráfico do resultado acumulado e dicas. Também gera `dados/relatorio.html`, com gráficos.
7. **Interface web**: a mesma partida no navegador.

Entre as mãos: **Enter** continua, **s** sai da mesa com as suas fichas, **p** pausa e salva.

### Comandos na sua vez (terminal)

| Comando   | Ação |
|-----------|------|
| `d` / `p` / `c` | desistir / passar / pagar (`c` passa quando não há aposta) |
| `a VALOR` | apostar ou aumentar **para** o valor total na rodada (ex.: `a 60`) |
| `t`       | all-in |
| `e`       | equity estimada contra mãos aleatórias e pot odds |
| `?`       | ajuda |

### Opções de linha de comando

```bash
python main.py --fichas 2000 --bots 3 --sb 10 --bb 20 --ante 2 --straddle --dificuldade dificil
python main.py --semente 42          # reproduz a mesma sequência de cartas
python main.py --sem-treinador       # desliga os comentários
python main.py --sem-simbolos        # usa e/c/o/p em vez de ♠♥♦♣
python main.py --dados outra_pasta   # onde ficam banco, históricos e relatórios
python main.py --web --porta 9000 --sem-navegador
```

## Valores padrão

| Item | Padrão |
|------|--------|
| Variante | Texas Hold'em No-Limit |
| Blinds | 5 / 10 · ante 0 · sem straddle (straddle = 2× BB, à esquerda do BB) |
| Stack inicial | 1000 fichas (100 big blinds) |
| Bots | 5 (6-max), dificuldade média; máximo 8 |
| Apostas | mínima 1 BB; aumento mínimo = último aumento; máximo = stack |
| Rake | nenhum |

## O que fica salvo (`dados/`, fora do git)

- `poker.db`: banco SQLite com as sessões, as estatísticas de cada mão sua, a mesa salva e o quiz.
- `historico/AAAA-MM-DD_sessaoNNN_pt.txt`: histórico das mãos em português.
- `historico/AAAA-MM-DD_sessaoNNN_pokerstars.txt`: o mesmo histórico no **formato do PokerStars**,
  que pode ser importado no PokerTracker 4, no Hold'em Manager 3 ou em sites de replay. Seu nome aparece como "Voce".
- `relatorio.html`: relatório com gráficos.

## Bots

| Nível | Como joga |
|-------|-----------|
| Fácil | Equity contra mãos aleatórias × pot odds, com erros de propósito. |
| Médio | Ranges de abertura, 3-bet e pagamento por posição; pós-flop por equity e pot odds, com apostas de ½ a ¾ do pote. |
| Difícil | Estima o range de cada oponente pela ação no pré-flop e pelo perfil observado (VPIP/PFR/AF), **adapta-se ao seu estilo** e faz continuation bets e semi-blefes. |

Cada bot também tem um estilo (conservador, equilibrado, agressivo ou solto).

## Sincronização opcional com o Supabase

Desligada por padrão: tudo funciona offline. Para ativar:

1. rode `supabase/schema.sql` no SQL Editor do seu projeto Supabase;
2. crie `dados/nuvem.json` com `{"url": "https://SEU-PROJETO.supabase.co", "chave": "SUA_SECRET_KEY"}`,
   ou defina `SUPABASE_URL` e `SUPABASE_KEY`.

Ao sair da mesa, as sessões encerradas são enviadas para a tabela `sessoes_poker`.
A tabela usa RLS sem políticas públicas, então só a chave secreta, que fica no seu computador, consegue gravar.

## Regras implementadas

- Blinds, ante, straddle, botão rotativo e regra de heads-up.
- Pote principal e side pots com qualquer número de all-ins, inclusive all-in só com o ante.
- Aposta não paga volta ao dono.
- Empates dividem o pote; a ficha ímpar vai para o primeiro à esquerda do botão.
- All-in menor que o aumento mínimo não reabre o aumento para quem já agiu.
- A cada mão, o jogo confere se as fichas na mesa são iguais a compras − retiradas e para com erro se não forem.

## Testes e integração contínua

`python -m unittest` roda 66 testes:

- ranking das mãos, empates e divisão do pote;
- 4000 situações aleatórias de potes comparadas com uma implementação de referência;
- mãos aleatórias com ante, straddle e all-ins;
- estatísticas, históricos (incluindo o formato PokerStars), banco, pausar e continuar;
- treinador, quiz, cenários, bots, API web e sincronização (com servidor falso).

O workflow `.github/workflows/testes.yml` roda os testes e uma partida completa simulada
no Ubuntu e no Windows, com Python 3.9, 3.11 e 3.13.

## Estrutura

```
main.py                  menu do terminal e opções de linha de comando
poker/cartas.py          cartas e baralho
poker/avaliador.py       ranking das mãos e desempates
poker/potes.py           pote principal, side pots e divisão
poker/mesa.py            motor da mão (emite eventos para os "ouvintes")
poker/narrador.py        eventos → texto em português
poker/historico.py       histórico em português e no formato PokerStars
poker/estatisticas.py    VPIP, PFR, 3-bet, WTSD, W$SD, AF, bb/100 e dicas
poker/persistencia.py    banco SQLite
poker/sessao.py          sessão de cash game (mesa + banco + histórico)
poker/relatorio.py       relatório em texto (gráfico ASCII) e HTML (SVG)
poker/ranges.py          força das 169 mãos, posições e ranges de abertura
poker/quiz.py            quiz pré-flop
poker/treinador.py       comentários sobre as suas decisões
poker/cenarios.py        cenários de prática
poker/bots.py            bots (fácil, médio, difícil)
poker/nuvem.py           sincronização opcional com o Supabase
poker/web/               servidor HTTP local e página HTML/JS
supabase/schema.sql      tabela para a sincronização
tests/                   testes automatizados
```

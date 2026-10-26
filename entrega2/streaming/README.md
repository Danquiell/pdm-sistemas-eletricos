# Streaming do clima (INMET) e junção com a energia

Esta pasta põe o clima do INMET dentro do GCP como se ele chegasse em tempo real e junta, por
usina e dia, o clima com a energia perdida que a entrega 1 calculou. É o que permite olhar um
dia marcado como anômalo pelo modelo e ver como estava o vento, a radiação e a chuva perto da
usina.

O "tempo real" é um replay: o produtor lê um recorte fixo do histórico do INMET (34 estações do
Nordeste, 01 a 19/08/2026, 14.521 leituras horárias) e publica uma leitura por vez no Pub/Sub,
a 20 por segundo. O resto do caminho é o mesmo que seria com dado chegando de verdade.

## Caminho do dado

```
snapshot_inmet_agosto2026.jsonl  (gerado pelo preparar.py, não fica no repositório)
  -> produtor.py            publica no tópico inmet-horario-stream
  -> Pub/Sub                assinatura push inmet-horario-processamento
  -> Cloud Run              serviço pipeline-ons-streaming, rota /inmet/pubsub (inmet_service.py)
  -> BigQuery bruto         sistema_eletrico.inmet_stream_raw          (tudo que chegou)
  -> BigQuery limpo         sistema_eletrico_silver.inmet_stream_horario
                            sistema_eletrico_silver.inmet_stream_rejeitados (com o motivo)
  -> view canônica          sistema_eletrico_gold.v_inmet_stream_horario  (sem reentregas)
  -> clima por dia          sistema_eletrico_gold.v_inmet_stream_diario
  -> clima + energia        sistema_eletrico_gold.v_energia_inmet_stream_diario
  -> API de anomalias       entrega2/inferencia, campo contexto_inmet da resposta
```

O mesmo serviço do Cloud Run tem uma segunda rota, `/pubsub` (`ons_legacy.py`), que recebe as
leituras de restrição do ONS do tópico `aula-pdm-sistema-eletrico` e grava em
`sistema_eletrico_silver.restricao_coff_stream`.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `preparar.py` | Cria as tabelas (`01_infra.sql`), congela o vínculo usina-estação de agosto em `inmet_replay_vinculos` e exporta o snapshot com o `manifesto.json` (lista de estações, número de leituras e SHA-256 do arquivo) |
| `produtor.py` | Publica o snapshot no Pub/Sub. Guarda o ponto onde parou em `checkpoint_<execução>.json` e continua dali se for interrompido |
| `main.py`, `inmet_service.py`, `ons_legacy.py` | O serviço do Cloud Run: rota do clima e rota do ONS |
| `contrato_referencia.py` | Regras de identidade do evento e de limpeza dos valores, usadas pelo serviço e pelos testes |
| `evento_inmet.schema.json` | Formato da mensagem do clima |
| `01_infra.sql` | Tabelas bruta, limpa e de rejeitados, e a view canônica |
| `02_views_pessoa3.sql` | Views de clima por dia e de clima + energia |
| `03_fila_de_erro.sh` | Liga a fila de erro (dead-letter) na assinatura do clima |
| `deploy.sh` | Publica o serviço do streaming no Cloud Run |
| `validar_pipeline.py` | Teste de aceite pelo Pub/Sub de verdade, numa execução `validacao_*` |
| `pessoa3.py` | Confere a view de clima + energia e recalcula o clima diário em Python, independente do SQL |
| `config_projeto.json` | Parâmetros do projeto e da API (contrato 1.1.0) |
| `openapi.json`, `predict_request.schema.json`, `predict_response.schema.json` | Contrato da API de anomalias |

## Ordem para montar do zero

Tudo no projeto `pdm-sistema-eletrico-2026`, região `us-central1`, com o gcloud logado
(o Cloud Shell já serve). Bibliotecas: `pip install -r requirements.txt`.

1. `python preparar.py`. Gera `snapshot_inmet_agosto2026.jsonl` e `manifesto.json` nesta pasta.
   O serviço recusa leitura de estação ou de snapshot que não esteja no manifesto, então o
   `manifesto.json` publicado no Cloud Run tem que ser o mesmo que o produtor usa.
2. Publicar o serviço: `bash deploy.sh`. Ele roda o
   `gcloud run deploy pipeline-ons-streaming --source . --region us-central1 --max-instances 1 --no-allow-unauthenticated --service-account pipeline-streaming@pdm-sistema-eletrico-2026.iam.gserviceaccount.com`
   com as demais configurações do serviço publicado.
   Fica com uma instância só porque a checagem de duplicata guarda os hashes em memória.
3. Criar o tópico `inmet-horario-stream` e a assinatura push `inmet-horario-processamento`
   apontando para `URL_DO_SERVICO/inmet/pubsub`, com token OIDC da conta
   `pubsub-push-pipeline` (a única com permissão de chamar o serviço).
4. `bash 03_fila_de_erro.sh`.
5. Rodar `02_views_pessoa3.sql` no BigQuery.
6. `python produtor.py --run-id demo_AAAAMMDD_NN`. A execução oficial é `demo_20261018_01`.
   Para uma nova, usar outro nome: o mesmo nome continua do checkpoint.
7. `python validar_pipeline.py`. Manda casos de propósito (republicação, conflito, valor com
   vírgula, tudo nulo, JSON quebrado) e confere onde cada um foi parar.
8. `python pessoa3.py --run-id demo_AAAAMMDD_NN --final`.

## Regras que valem para quem lê os dados

**Duplicatas.** O Pub/Sub pode entregar a mesma mensagem mais de uma vez. A tabela limpa guarda
todas; a view `v_inmet_stream_horario` deixa uma por `replay_run_id` + `event_id`. Se a mesma
leitura chegar com valores diferentes, ela sai da view e vai para os rejeitados com
`DUPLICATE_CONFLICT`: nenhuma das duas versões é escolhida no chute.

**Execuções.** Cada rodada do produtor tem um `replay_run_id`. A view de clima + energia tem
uma cópia das 3.705 linhas de energia para cada execução, então qualquer soma precisa filtrar
a execução. As execuções `validacao_*` são testes e ficam fora dessa view desde 25/10/2026;
antes, uma soma sem filtro saía 5 vezes maior que a Gold.

**Leitura atrasada.** As views não guardam resultado: cada consulta recalcula a partir da
tabela limpa. Uma leitura que chega depois entra na próxima consulta e muda o total daquele
dia sem aviso. O campo `atualizado_em_utc` diz quando chegou a última leitura usada no dia.
Quem precisa de um número fixo (um relatório, por exemplo) deve anotar o `atualizado_em_utc`
junto. A API guarda o clima em memória por até 10 minutos, então pode levar esse tempo para
mostrar uma leitura nova. No replay de agosto, o produtor terminou em 18/10/2026 e nada chegou
depois, então os totais estão fechados.

**Clima incompleto.** O `status_contexto` diz se o clima do dia serve: `APTO_PARA_CONTEXTO`
quando a eólica tem pelo menos 80% das horas com vento, ou a solar tem pelo menos 80% das
horas de radiação entre 8 h e 16 h e 80% das horas com temperatura; `PARCIAL` quando não;
`SEM_VINCULO` quando a usina não tem estação; `AGUARDANDO_STREAM` quando o clima ainda não
chegou. Na execução oficial: 3.549 aptos e 156 parciais.

**Fila de erro.** Mensagem que o serviço recusa com erro 5xx cinco vezes vai para o tópico
`inmet-horario-stream-dlq` e fica guardada 7 dias na assinatura
`inmet-horario-stream-dlq-guarda`. Mensagem com dado errado não é erro 5xx: ela é gravada nos
rejeitados com o motivo e confirmada.

## Rota do ONS

As leituras do ONS no tópico `aula-pdm-sistema-eletrico` chegavam por dois caminhos: a
assinatura push `pipeline-ons-push` (Cloud Run, com limpeza e enriquecimento, grava em
`restricao_coff_stream`) e a assinatura BigQuery `aula-pdm-sistema-eletrico-bq` (gravação
direta, sem limpeza, em `restricao_coff_pubsub`). A segunda foi apagada em 25/10/2026. Nenhuma
view usava `restricao_coff_pubsub`; a tabela continua lá com as 85 linhas que recebeu.

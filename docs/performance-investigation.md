# Investigação de desempenho — 19/10/2026

## Estado da correção

O documento preserva o histórico da investigação. As seções iniciais descrevem
a análise anterior à primeira build; as atualizações abaixo registram as
compilações autorizadas, as entregas e as comparações posteriores. O resultado
mais recente do mapa estabilizado foi 52,78 → 56,08 FPS, ainda abaixo da
cadência nativa. Os detalhes e limites dessa comparação estão na seção final.

O manifesto ARM9 principal continua com `authoritative_entry_points=true`.
O novo banco usa `--validate-live-bytes`, assim como os bancos principais.
Não houve alteração de velocidade, descarte de quadros, interpolação,
renderizador, buffer de áudio ou scheduler.

## Evidência da lacuna

A tabela SDK no ARM9 da ROM USA informa estas cópias, nesta ordem:

| Origem | Destino | Bytes |
| --- | --- | --- |
| `0x02043380` | `0x01FF8000` | `0x7FA0` |
| `0x0204B320` | `0x027E0000` | `0x840` |
| `0x0204BB60` | `0x02043380` | `0x42500` |

O pipeline anterior emitia o ARM9 original e o alias ITCM, mas não emitia
o bloco main RAM após autoload. Os 1.042 seeds já existentes em
`config/seeds/arm9_arm9_01ff7820.toml` correspondem a essa cópia: o nome
registra a base que a imagem inteira teria se fosse deslocada, não um
intervalo ITCM a executar.

`prepare_nsmb.py` agora lê a tabela, extrai somente os `0x42500` bytes
instalados e produz `arm9_runtime.bin`/`.toml`. Rejeita tabelas fora dos
limites, assinatura ambígua, fontes inválidas e múltiplas cópias main RAM.
Os seeds devem estar dentro do bloco. `emit_all_banks.py` emite
`nsmb_arm9_runtime`, com quatro shards e validação dos bytes vivos.

Na captura `title-baseline-local`, 39 páginas completas desse bloco são
idênticas byte a byte às páginas vivas. Elas somaram 1.755.191 retomadas
do interpretador. Isso demonstra uma lacuna de cobertura; não mede qual
porcentagem do tempo de CPU será recuperada.

## Medições do binário anterior

Artefatos locais, ignorados pelo Git:
`build-runner/performance-checks/`. Cada execução tem identidade explícita,
`--no-save`, diretório isolado, hash do runner/ROM, comandos, rota, amostras,
estatísticas, cobertura e capturas PPM das duas telas. O perfil usa o
renderizador compute automático, layout stacked e resolução nativa.
As configurações pessoais de `dist-playable` não são carregadas nesse
diretório isolado; o teclado usa os padrões do runner (`Z=A`, `X=B`).

| Execução / janela | Quadros | FPS | Emulação ms/quadro | Apresentação ms/quadro | Drain ms/quadro |
| --- | ---: | ---: | ---: | ---: | ---: |
| `title-baseline-local`, boot/menu | 908 | 50,39 | 12,12 | 0,70 | 3,29 |
| `route-long`, introdução/aquecimento/mapa | 3.600 | 42,17 | 22,92 | — | ~0,003 |
| `route-long`, mapa com menu de pausa aberto | 302 | 46,17 | 20,97 | — | ~0,003 |
| `route-long`, fase pausada | 126 | 59,83 | 10,44 | — | ~0,003 |
| `first-level-baseline`, mapa ocioso | 301 | 40,66 | 23,93 | 0,61 | 0,003 |
| `first-level-baseline`, correr na fase 1-1 | 123 | 59,83 | 13,91 | 0,60 | 0,003 |
| `first-level-baseline`, correr e pular na fase 1-1 | 94 | 59,82 | 13,85 | 0,65 | 0,004 |
| `first-level-baseline`, mapa com pausa aberta | 128 | 40,03 | 24,19 | 0,74 | 0,003 |

O nome `map` na rota exploratória corresponde visualmente ao mapa com
menu de pausa aberto. Os segmentos exploratórios `run-right` e `jump`
incluem movimento no mapa e entrada na fase, não uma janela de gameplay
estável. Não devem ser usados como benchmark de movimento dentro da fase.

A sessão `route-long` encerrou normalmente após 6.637 quadros / 153,022 s
(43,373 FPS globais), sem dispatch-miss nem falha terminal. O log registrou
7.504 callbacks de underrun, zero erros de fila, maior emulação de 49,7 ms
e 157 quadros com emulação acima de 32 ms. O contador de underruns conta
callbacks, não necessariamente falhas audíveis independentes. A captura
final confirma fase 1-1 e menu de pausa; não valida o jogo completo.

A rota corrigida, `tools/routes/nsmb-first-level.json`, foi executada em
`first-level-baseline`: 6.755 quadros em 152,348 s, média global 44,339 FPS,
6.958 callbacks de underrun, zero erros de fila, pico de emulação 50,9 ms
e 146 quadros acima de 32 ms. Encerrou com código zero, sem dispatch-miss,
falha terminal ou apresentações sintéticas. As capturas confirmam entrada
na fase, movimento, morte (vidas 5→4), reinício, salto, nova morte (4→3),
pausa e retomada no mapa. As janelas de gameplay de 123 e 94 quadros são
curtas e não demonstram estabilidade numa fase inteira.

No mapa ocioso, o ARM9 interpretou ~122.808 instruções/quadro, contra
~55.462 na janela correndo. Com pausa aberta no mapa, foram ~236.084.
Essas contagens não são porcentagens de tempo. As 44 páginas completas
do bloco runtime presentes nessa segunda captura também coincidem com
o novo binário extraído; a cobertura não reportou páginas descartadas.
O runner das três rotas tem SHA-256
`8cedf2e23268e8ced99e422c8a46289dd38555bc1558b4c05d6179c2442ba585`.

O custo de apresentação é pequeno nessas janelas. A espera no drain some
nos trechos lentos, enquanto a emulação excede o orçamento de ~16,72 ms.
Isso sustenta investigar cobertura/CPU antes de alterar a sincronização.
Os contadores de dispatch/retorno são candidatos a perfil, não percentuais
de custo de CPU.

## Limitações da coleta

`tools/measure_nsmb.py` consulta contadores cumulativos via TCP a cada
~250 ms. Os tempos são médias por janela; não são amostras individuais de
quadros. Não é possível inferir P50/P95/P99 por quadro desses dados.
As durações da rota são mínimas: consulta e injeção só são atendidas entre
quadros, portanto há overshoot, registrado nos contadores before/after.
Os hashes de framebuffer não são uma prova de equivalência entre rotas
cujos inputs não tenham ocorrido exatamente no mesmo quadro.

Capturas são feitas fora da janela concluída e pedem sincronização de
framebuffer, que força dois quadros de renderização em CPU. A próxima
janela pode conter esse custo. Não compare janelas muito curtas como
medidas de desempenho. Diagnósticos e a coleta também têm custo. O host
não foi certificado como ocioso, e os resultados não representam hardware
outras máquinas. Não foi feita avaliação humana da qualidade do som.

## Validação executada sem build

- Sete testes unitários de extração e rejeição de tabelas inválidas passaram.
- Preparação da ROM em `performance-checks/prepared-runtime` confirmou
  origem, destino, tamanho, 1.042 seeds e manifesto principal authoritative.
- Comparação com 39 páginas vivas completas passou byte a byte.
- Sintaxe dos scripts Python e `git diff --check` conferidos.
- Nenhum banco C foi gerado/compilado e nenhum executável foi substituído.

## Build e comparação pendentes na investigação inicial

Na raiz do projeto, com os caches atuais, executar localmente:

```powershell
& C:/msys64/mingw64/bin/cmake.exe --build build-launcher --target nsmb_generate_banks
& C:/msys64/mingw64/bin/cmake.exe -S ndsrecomp/runner -B build-runner
& C:/msys64/mingw64/bin/cmake.exe --build build-runner --target nds_runner
```

A reconfiguração do runner após a geração é necessária para que o registro
automático inclua `nsmb_arm9_runtime_dispatch.c`. A biblioteca do projeto
principal também declara os novos shards como byproducts para incluí-los
na primeira geração, antes de aparecerem no glob de fontes.

Preservar o runner antigo para comparação, sem sobrescrever os saves.
O coletor aceita qualquer caminho de runner e gera diretórios novos:

```powershell
python tools/measure_nsmb.py --runner build-runner/nds_runner.exe --route tools/routes/nsmb-first-level.json --out build-runner/performance-checks/first-level-after-01
```

Repetir a mesma rota em sessões intercaladas com os dois runners e conferir
as capturas de cada segmento. Comparar gameplay separado de boot, mapa,
transições, morte/reinício e pausa. Confirmar redução de Tier 3 e de tempo
de emulação, áudio, input, ausência de falhas e encerramento normal.
Se a rota deixar de atingir a mesma cena, descartar a comparação.

Ainda faltam medição por quadro com percentis, perfil de CPU com símbolos,
comparação A/B do banco novo, qualidade de áudio e uma sessão longa em
várias fases. A meta de 59–59,5 FPS em gameplay não foi demonstrada.

## Atualização: build solicitada e entregue

Após autorização explícita do usuário, a geração dos bancos e o build de
`nds_runner` concluíram com sucesso. O registro inclui
`g_dispatch_nsmb_arm9_runtime`. O launcher foi conferido pelo seu target
de build, que já estava atualizado.

O novo runner foi copiado para `dist-playable/nds_runner.exe` e
`build-launcher/nds_runner.exe`. SHA-256 das três cópias:
`a93d07d9bd18af621a82e94d2dea4388d1e6b5ca7184b67e62afb1f54095aa3a`.
O runner anterior está preservado em
`build-runner/performance-checks/pre-autoload-build/nds_runner.exe`.
Hashes da ROM, dos saves e das configurações de `dist-playable` foram
comparados antes/depois e permaneceram iguais.

Os testes existentes `direct_boot_test` e `dispatch_lookup_test` passaram.
O teste curto do runner novo renderizou o menu e encerrou normalmente após
915 quadros, sem dispatch-miss, falha terminal, erro de fila ou apresentação
sintética. Registrou 9 callbacks de underrun e maior emulação de 30,4 ms.
Evidências em `build-runner/performance-checks/new-build-smoke/`, incluindo
`menu.png`, `runner.log` e `deployed-files.json`.

Esse teste de abertura inclui boot e aquecimento. Não substitui comparação
A/B nem demonstra estabilidade em fases; os testes de gameplay serão
realizados pelo usuário.

## Correções de cobertura do mapa — 20/10/2026

Após o usuário validar gameplay, castelo e saves e autorizar novas correções
e build, foram preparados dois ajustes restritos ao título:

- `config/seeds/arm9_main_interiors.toml` declara 861 retomadas ARM observadas
  dentro de funções já delimitadas em `config/symbols.txt`. Cada registro
  contém endereço, tamanho e proprietário. `prepare_nsmb.py` exige mesmo
  modo, alinhamento e limite final idêntico ao do proprietário. Entradas
  sem proprietário, com tamanho zero ou fora dos limites são rejeitadas.
  O ARM9 principal continua authoritative; não recebe os antigos seeds
  sem tamanho da imagem anterior ao autoload.
- `config/seeds/arm9_arm9_overlay_009_020cc2e0.toml` declara 1.196 alvos
  observados na rota, conferidos contra páginas capturadas correspondentes
  ao overlay 009. Inclui chamadas/indiretos e retomadas omitidas na primeira
  geração do banco. O pipeline agora emite e registra `nsmb_arm9_ov009`.

Os bancos principal e overlay 009 mantêm `--validate-live-bytes`. Todas as
22.149 linhas de dispatch ARM9 principal e 14.136 do overlay 009 têm
descritor de validação. Os 861 pontos adicionais aparecem no dispatch.
Nenhum código do runtime, scheduler, áudio ou renderizador foi alterado.

O caso que motivou a mudança era `0x0200EAF8`, dentro da função declarada
`0x0200EACC..0x0200EB00`: o C gerado desviava para esse endereço, mas não
o emitia após o primeiro retorno. Agora esse trecho tem uma entrada
delimitada, sem permitir descoberta recursiva fora da função.

### Comparação no mapa

Mesma rota, ROM, resolução e layout separado. Os artefatos antes da mudança
estão em `build-runner/performance-checks/map-investigation/separate-baseline`;
os posteriores, em `build-runner/performance-checks/map-fix/`.

| Janela | Antes FPS | Final FPS | Antes emulação ms/q | Final emulação ms/q |
| --- | ---: | ---: | ---: | ---: |
| Mapa estabilizado | 52,78 | 56,08 | 17,48 | 16,28 |
| Nó à direita ocioso | 51,89 | 56,65 | — | — |
| Nó à esquerda ocioso | 54,33 | 56,46 | — | — |
| Introdução e chegada ao mapa, janela mista | 51,47 | 53,60 | 17,40 | 16,42 |

Na janela estabilizada, a interpretação ARM9 caiu de ~22.216 para ~5.548
instruções/quadro. Só a mudança de retomadas internas já havia medido
55,78 FPS e 16,35 ms de emulação/quadro. A inclusão do overlay 009 não
mostrou ganho isolado relevante: uma primeira versão mediu 55,69 FPS e
a versão completada, 56,08. Essa diferença não demonstra ganho próprio
do overlay e não deve ser apresentada como tal.

O mapa ainda ficou abaixo da cadência nativa nesses testes. As médias dos
primeiros quadros do menu permaneceram próximas às anteriores; incluem
startup e espera de áudio. A janela de introdução não isola o quadro do
raio atingindo o castelo. Não foi demonstrada a eliminação de cada engasgo
nesses momentos nem foram medidos percentis por quadro.

As sessões foram sequenciais, com diagnósticos e snapshots entre janelas;
não são um A/B intercalado com host certificado como ocioso. As durações
de input têm overshoot, registrado nos artefatos. As capturas confirmam o
mesmo mapa e não mostram regressão visual aparente, mas não constituem
comparação bit a bit. A melhora precisa ser confirmada no teste do usuário.

### Build e validação

As builds intermediária e final concluíram. Os 12 testes Python passaram,
incluindo rejeição de retomadas fora da função e da região inicial do
autoload. Os testes existentes de boot direto e busca de dispatch passaram.
O teste final do mapa encerrou normalmente após 5.936 quadros, sem
dispatch-miss, falha terminal, erro de fila ou apresentação sintética.
Registrou 1.984 callbacks de underrun e pico de emulação de 26,0 ms;
underruns ainda não estão eliminados.

O runner anterior foi preservado em
`build-runner/performance-checks/map-fix/previous-runner.exe`; a versão
intermediária, em `interiors-only-runner.exe`. Comparação numérica em
`map-fix/comparison.json` e captura lado a lado em `map-before-after.png`.
O pipeline também regenera os manifests TOML em `generated/inputs/`.

A verificação final de gameplay completou 5.171 quadros e encerrou normalmente.
As capturas confirmam fase 1-1, movimento, duas mortes e reinício; as janelas
correndo (128 quadros) e pulando (96 quadros) mediram 59,83 FPS. São janelas
curtas, não uma certificação de todas as fases. O comando de pausa dessa rota
coincidiu com a transição de morte e não foi considerado uma validação de pausa.

Uma execução adicional com o mapa parado confirmou visualmente a abertura
do menu de pausa e a retomada; evidência em `map-fix/final-pause/pause-resume.png`.
As três execuções finais encerraram normalmente, sem dispatch-miss ou falha
terminal. Esses testes usaram `--no-save`; os saves pessoais não foram testados
nem modificados nesta etapa.

Runner entregue em `build-runner/nds_runner.exe`, `build-launcher/nds_runner.exe`
e `dist-playable/nds_runner.exe`, com SHA-256 idêntico:
`ee7507d2d550bcfbe189b138dbd03f92b6373046a8bc2bc23943490dd5abdbcf`.
Os hashes da ROM, dos saves e das configurações pessoais permaneceram iguais
antes/depois. O manifesto da entrega está em `map-fix/final-build.json`.
O launcher não precisou de recompilação; seu target estava atualizado.

### Segunda investigação: animações e movimentação no mapa (20/10/2026)

Com o runner acima, o mapa no save com progresso mediu 55,27 FPS parado
(16,48 ms de emulação/quadro) e 53,03 FPS no agregado dos deslocamentos
(17,18 ms). A interpretação ARM9 ficou praticamente igual: 5.718 e 5.686
instruções/quadro. Na introdução, a janela central com Bowser Jr. e Peach
no mapa mediu 49,94 FPS; o trecho final, 51,27 FPS. As capturas não isolam
o quadro do raio. Dados e limitações estão em
`build-runner/performance-checks/animation-investigation/analise-animacoes.md`.

A amostragem da thread principal encontrou custo disperso no código
recompilado, no dispatch/validação e nos helpers de instrução. O grupo de
dispatch/validação/retorno representou 19,7% das amostras dentro do módulo
no mapa parado e 23,8% em deslocamento. São amostras de RIP, sem pilhas;
helpers compartilhados não permitem atribuir todo o custo à interpretação
ou a uma rotina de animação específica. Também houve aumento de custo de
renderização/sincronização na introdução, ainda sem separar execução da GPU
e espera. Essas medições não sustentam promover mais instruções como única
solução para a queda ao movimentar o personagem.

### Alteração nos fontes: agrupamento de fallthroughs validados

O emissor passa a solicitar `--coalesce-fallthroughs` apenas nos bancos
`nsmb_arm9_itcm` e `nsmb_arm9_runtime`. O mecanismo já existente no framework
agrupa trechos consecutivos de mesmo modo e origem, dentro de uma página de
4 KiB, evitando retornos intermediários ao dispatcher. Mantém a validação
dos bytes vivos e os pontos de retomada; chamadas diretas otimizadas não
foram ativadas nesta alteração.

A emissão agora segue a ordenação dos nomes completos `*_dispatch.c` usada
pelo registro de bancos do runner. Antes de agrupar um banco, passa ao
recompilador os dispatches anteriores do título e os dispatches de BIOS e
firmware. Também considera arquivos extras anteriores existentes na pasta
do título. Uma entrada encontrada nesses bancos impede agrupamento através
dela, preservando sua prioridade. Arquivos esperados ausentes interrompem
a emissão. A inclusão conservadora dos dois CPUs e das duas variantes de
BIOS pode limitar o agrupamento, mas não remove essa proteção.

`NSMB_COALESCE_FALLTHROUGHS` fica `ON` por padrão no CMake. Para comparação,
configurar `-DNSMB_COALESCE_FALLTHROUGHS=OFF`; no script, usar
`--no-coalesce-fallthroughs`. Mudanças nessa opção ou nos dispatches do
framework invalidam o stamp de emissão. Caso o runner use um
`NDS_GENERATED_DIR` personalizado, configurar `NSMB_PRECEDING_DISPATCH_DIR`
para a mesma pasta; o padrão é `${NDSRECOMP_ROOT}/generated`.

Nesta etapa, passaram os 22 testes Python: 12 de preparação e 10 novos de
ordenação, prioridade, arquivos ausentes, validação obrigatória, escopo,
modo de controle, emissão inicial simulada e interrupção em falha. Os testes
novos usam um subprocesso simulado, sem executar o recompilador. O diretório
temporário precisou ser direcionado para dentro do projeto por restrição
de acesso do ambiente Windows.

Não houve build, geração dos bancos C, troca do executável nem nova medição
de FPS nesta etapa. A compilação, a contagem efetiva de fallthroughs
agrupados e a validação visual/de desempenho da mudança ficam pendentes da
próxima build local. Não há ganho de FPS demonstrado para esta alteração.
